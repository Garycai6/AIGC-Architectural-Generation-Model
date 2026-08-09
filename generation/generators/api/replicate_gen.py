import asyncio
import urllib.request
from pathlib import Path

from generation.generators.api.prompt import build_negative_prompt, build_prompt
from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams

# Replicate ControlNet SDXL model(真调验证于 2026-08-05,model_type=canny
# 接受线稿作条件图,返回遵循结构的真图)。版本哈希固定,防上游变动。
SDXL_MODEL = (
    "replicategithubwc/controlnet-sdxl:"
    "73cd44907a04eca8931003dbcd092021553fd813df32a1b4a3a238bed47cf1e4"
)
CONTROLNET_TYPE = "canny"
CONTROLNET_STEPS = 30
CONTROLNET_GUIDANCE = 7.5

FACADE_FILE = "facade.png"
FLOORPLAN_FILE = "floorplan.png"


class ApiGeneratorError(Exception):
    """API generator configuration / invocation error."""


class ApiGenerator:
    """Replicate SDXL + ControlNet generator — implements the Generator protocol.

    Flow: simulator line-art as ControlNet condition images -> SDXL real
    images (facade + floorplan).
    """

    def __init__(self, replicate_client=None, model: str = SDXL_MODEL):
        if replicate_client is None:
            raise ApiGeneratorError("replicate client not provided (set replicate_api_token)")
        self._client = replicate_client
        self._model = model

    def _call_sdxl(self, prompt: str, control_image: Path, out_path: Path) -> None:
        """Synchronous Replicate ControlNet SDXL call (runs in thread pool)."""
        with open(control_image, "rb") as f:
            output = self._client.run(
                self._model,
                input={
                    "prompt": prompt,
                    "negative_prompt": build_negative_prompt(),
                    "image": f,
                    "model_type": CONTROLNET_TYPE,
                    "num_inference_steps": CONTROLNET_STEPS,
                    "guidance_scale": CONTROLNET_GUIDANCE,
                    "seed": 42,
                },
            )
        # output is a list of file URLs; the last item is the real generated
        # image (earlier items are ControlNet condition/edge maps).
        file_url = output[-1] if isinstance(output, list) else output
        urllib.request.urlretrieve(str(file_url), str(out_path))

    async def _render_facade_sdxl(self, params, scheme_id, out_dir, lang) -> None:
        """Facade goes through SDXL + ControlNet (facade_line.png is the
        condition image); floorplan stays the simulator line-art."""
        prompt = build_prompt(params, "facade", lang)
        control = out_dir / "facade_line.png"
        await asyncio.to_thread(self._call_sdxl, prompt, control, out_dir / FACADE_FILE)

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: Path,
        lang: str = "zh",
    ) -> GenerationArtifact:
        # 1. Generate facade line-art as ControlNet condition image, and
        #    floorplan line-art as the floorplan output (accurate programmatic
        #    drawing — SDXL cannot produce correct floor plans, verified 2026-08-05).
        await render_scheme(params, scheme_id, out_dir, lang)
        # 2. Rename facade line-art to _line suffix (condition image)
        line_facade = out_dir / FACADE_FILE
        facade_line = out_dir / "facade_line.png"
        if line_facade.exists():
            line_facade.rename(facade_line)
        # 3. One SDXL call (facade only); floorplan stays as simulator line-art
        await self._render_facade_sdxl(params, scheme_id, out_dir, lang)
        # 4. Clean up the facade condition image
        facade_line.unlink(missing_ok=True)
        return GenerationArtifact(
            scheme_id=scheme_id,
            images=[
                ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
                ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
            ],
        )


__all__ = ["ApiGenerator", "ApiGeneratorError"]
