from typing import Literal

from pydantic import BaseModel, Field, model_validator

Style = Literal["modern", "neoclassic", "european", "nordic"]
Material = Literal["glass", "stone", "brick", "wood"]
Roof = Literal["flat", "pitched", "hipped"]
Environment = Literal["urban", "suburb", "rural", "seaside"]
ViewAngle = Literal["front", "front-3-4"]

STYLE_NAMES = ["modern", "neoclassic", "european", "nordic"]

FLOOR_HEIGHT_M = 3.2  # 默认层高


class BuildingParams(BaseModel):
    """建筑生成参数——所有生成流程的输入契约。"""

    style: Style
    floors: int = Field(ge=1, le=6)
    width_m: float = Field(ge=6, le=20)
    depth_m: float = Field(ge=5, le=18)
    height_m: float | None = Field(default=None, gt=0)
    materials: list[Material] = Field(min_length=1)
    roof: Roof
    environment: Environment
    view_angle: ViewAngle = "front"
    color_scheme: str | None = None

    @model_validator(mode="after")
    def default_height(self) -> "BuildingParams":
        if self.height_m is None:
            self.height_m = self.floors * FLOOR_HEIGHT_M
        return self
