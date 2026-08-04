from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from generation.params.model import BuildingParams


class ImageRef(BaseModel):
    kind: Literal["facade", "floorplan"]
    url: str


class GenerationArtifact(BaseModel):
    scheme_id: str
    images: list[ImageRef]


class Generator(Protocol):
    """生成器契约——模拟器与未来 API/真实模型共用,网页层零改动。"""

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: Path,
        lang: Literal["en", "zh"] = "zh",
    ) -> GenerationArtifact: ...
