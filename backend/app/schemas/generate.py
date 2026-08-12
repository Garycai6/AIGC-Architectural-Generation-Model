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
    remaining_quota: int = 0  # 本次消费后的剩余次数(无头请求报满额)
