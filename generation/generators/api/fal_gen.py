import asyncio
import urllib.request
from pathlib import Path

from generation.generators.api.prompt import build_negative_prompt, build_prompt
from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams

# fal ControlNet SDXL(canny 版,与 replicate 的 controlnet-sdxl 对等)。
FAL_MODEL = "fal-ai/fast-sdxl-controlnet-canny"
CONTROLNET_CONDITIONING_SCALE = 0.5  # 与 replicate 的 condition_scale 0.5 对齐
FAL_STEPS = 30
FAL_GUIDANCE = 7.5
# 排队开始前等待上限(不含处理时长)
FAL_WAIT_SECONDS = 300

FACADE_FILE = "facade.png"
FLOORPLAN_FILE = "floorplan.png"


class FalGeneratorError(Exception):
    """Fal generator configuration / invocation error."""


class FalGenerator:
    """Fal SDXL + ControlNet generator — implements the Generator protocol.

    Flow: simulator line-art as ControlNet condition image (uploaded to fal
    storage for a public URL) -> SDXL real facade; floorplan stays simulator
    line-art.
    """

    def __init__(self, fal_client=None, model: str = FAL_MODEL):
        if fal_client is None:
            raise FalGeneratorError("fal client not provided (set fal_api_key)")
        self._client = fal_client
        self._model = model

    async def _upload_lineart(self, path: Path) -> str:
        """Upload the condition image to fal storage, return its public URL."""
        return await asyncio.to_thread(self._client.upload_file, path)

    async def _call_fal(self, prompt: str, control_url: str, out_path: Path) -> None:
        sdxl_input = {
            "prompt": prompt,
            "negative_prompt": build_negative_prompt(),
            "control_image_url": control_url,
            "controlnet_conditioning_scale": CONTROLNET_CONDITIONING_SCALE,
            "num_inference_steps": FAL_STEPS,
            "guidance_scale": FAL_GUIDANCE,
            "image_size": {"width": 1024, "height": 1024},
            "num_images": 1,
            "seed": 42,
        }
        handle = await self._client.submit_async(
            self._model, arguments=sdxl_input, start_timeout=FAL_WAIT_SECONDS
        )
        result = await handle.get()  # get() 阻塞轮询直到完成
        url = result["images"][0]["url"]
        urllib.request.urlretrieve(url, str(out_path))

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: Path,
        lang: str = "zh",
    ) -> GenerationArtifact:
        # 与 ApiGenerator 同骨架:线稿条件图 → 真模型 facade,floorplan 留模拟器线稿
        await render_scheme(params, scheme_id, out_dir, lang)
        line_facade = out_dir / FACADE_FILE
        facade_line = out_dir / "facade_line.png"
        if line_facade.exists():
            line_facade.rename(facade_line)
        try:
            prompt = build_prompt(params, "facade", lang)
            control_url = await self._upload_lineart(facade_line)
            await self._call_fal(prompt, control_url, out_dir / FACADE_FILE)
        finally:
            facade_line.unlink(missing_ok=True)
        return GenerationArtifact(
            scheme_id=scheme_id,
            images=[
                ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
                ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
            ],
        )


__all__ = ["FalGenerator", "FalGeneratorError", "FAL_MODEL"]
