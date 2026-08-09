import asyncio
import urllib.request
from pathlib import Path

import replicate

from generation.generators.api.prompt import build_negative_prompt, build_prompt
from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams

# Replicate SDXL model (validation phase uses flux-schnell; replace
# with ControlNet-capable SDXL model after real-call validation).
# NOTE: actual model must be configured per ControlNet support; see
# real-call validation step.
SDXL_MODEL = "black-forest-labs/flux-schnell"
CONTROLNET_MODEL = "black-forest-labs/flux-schnell"  # placeholder, replace at validation

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
        """Synchronous Replicate SDXL call (runs in thread pool)."""
        with open(control_image, "rb") as f:
            output = replicate.run(
                self._model,
                input={
                    "prompt": prompt,
                    "negative_prompt": build_negative_prompt(),
                    "control_image": f,
                },
            )
        # output is a list of file URLs; download the first to out_path
        file_url = output[0] if isinstance(output, list) else output
        urllib.request.urlretrieve(str(file_url), str(out_path))

    async def _render_with_sdxl(self, params, scheme_id, out_dir, lang, kind) -> None:
        prompt = build_prompt(params, kind, lang)
        control = out_dir / ("facade_line.png" if kind == "facade" else "floorplan_line.png")
        await asyncio.to_thread(
            self._call_sdxl,
            prompt,
            control,
            out_dir / (FACADE_FILE if kind == "facade" else FLOORPLAN_FILE),
        )

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: Path,
        lang: str = "zh",
    ) -> GenerationArtifact:
        # 1. Generate two line-art images as ControlNet condition images
        await render_scheme(params, scheme_id, out_dir, lang)
        # 2. Rename to _line suffix (condition images), avoid overwriting real images
        line_facade = out_dir / FACADE_FILE
        line_floorplan = out_dir / FLOORPLAN_FILE
        facade_line = out_dir / "facade_line.png"
        floorplan_line = out_dir / "floorplan_line.png"
        if line_facade.exists():
            line_facade.rename(facade_line)
        if line_floorplan.exists():
            line_floorplan.rename(floorplan_line)
        # 3. Two SDXL calls (facade + floorplan)
        await self._render_with_sdxl(params, scheme_id, out_dir, lang, "facade")
        await self._render_with_sdxl(params, scheme_id, out_dir, lang, "floorplan")
        # 4. Clean up line-art condition images (keep real images)
        facade_line.unlink(missing_ok=True)
        floorplan_line.unlink(missing_ok=True)
        return GenerationArtifact(
            scheme_id=scheme_id,
            images=[
                ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
                ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
            ],
        )


__all__ = ["ApiGenerator", "ApiGeneratorError"]
