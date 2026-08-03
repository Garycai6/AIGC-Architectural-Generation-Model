from typing import Literal

from pydantic import BaseModel

from generation.params.model import BuildingParams


class GenerateRequest(BaseModel):
    params: BuildingParams
    lang: Literal["en", "zh"] = "zh"


class GenerationResponse(BaseModel):
    scheme_id: str
    description: str
    images: list[str] = []
