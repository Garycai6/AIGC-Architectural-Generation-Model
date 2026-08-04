from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from generation.params.model import (  # noqa: F401 模块契约,供后续任务使用
    FLOOR_HEIGHT_M,
    BuildingParams,
)

MAX_WIDTH_PX = 640
MAX_HEIGHT_PX = 480


class MaterialPalette(BaseModel):
    main: str
    accent: str
    trim: str


class WindowRect(BaseModel):
    x: int
    y: int
    w: int
    h: int
    cross: bool = True
    arch: bool = False


class RoofGeometry(BaseModel):
    kind: Literal["flat", "pitched", "hipped"]
    ridge_y: int | None = None
    has_eaves: bool = True


class CorniceSpec(BaseModel):
    has: bool
    thickness: int = 4
    y: int | None = None


class StyleConfig(ABC):
    window_ratio: tuple[float, float] = (1.0, 1.0)
    window_arch: bool = False

    @abstractmethod
    def cornice(self, width_px: int) -> CorniceSpec: ...

    @abstractmethod
    def apply_palette(self, mat: MaterialPalette) -> MaterialPalette: ...

    @abstractmethod
    def build_roof_geom(self, params: BuildingParams) -> RoofGeometry: ...


MATERIAL_COLORS: dict[str, MaterialPalette] = {
    "glass": MaterialPalette(main="#b8d8e8", accent="#e8f4f8", trim="#5b7f95"),
    "stone": MaterialPalette(main="#d9d2c0", accent="#efe9d8", trim="#8a8270"),
    "brick": MaterialPalette(main="#c0693f", accent="#e5d8c8", trim="#7a4a2b"),
    "wood": MaterialPalette(main="#b5936b", accent="#dcc9a8", trim="#6e5637"),
}


class FacadeSpec(BaseModel):
    width_px: int
    height_px: int
    floors: int
    windows: list[WindowRect]
    roof: Literal["flat", "pitched", "hipped"]
    style: str
    roof_geom: RoofGeometry
    cornice: CorniceSpec
    palette: MaterialPalette


def _roof_geom(params: BuildingParams) -> RoofGeometry:
    """按 roof 参数生成屋顶几何。非法值显式抛错,不静默兜底。"""
    if params.roof == "flat":
        return RoofGeometry(kind="flat", ridge_y=None)
    if params.roof == "pitched":
        return RoofGeometry(kind="pitched", ridge_y=20)
    if params.roof == "hipped":
        return RoofGeometry(kind="hipped", ridge_y=30)
    raise ValueError(f"Unknown roof kind: {params.roof}")


def _window_cols(width_m: float) -> int:
    # 按建筑面宽推导窗列数:6-10m 两列,11-20m 三列
    return 2 if width_m < 11 else 3


def _window_rows(floors: int, height_px: int, margin: int) -> tuple[list[int], int]:
    """按层数在画布高度内均分楼层,返回每层窗的 y 坐标与统一的窗高。

    窗在层内垂直居中,保证任意 floors(1-6)下窗口都不超出画布。
    """
    avail_h = height_px - 2 * margin
    floor_h = avail_h // floors
    window_h = max(20, floor_h - 24)
    ys = [margin + f * floor_h + (floor_h - window_h) // 2 for f in range(floors)]
    return ys, window_h


def build_facade_spec(
    params: BuildingParams, width_px: int = 640, height_px: int = 480
) -> FacadeSpec:
    scale = width_px / MAX_WIDTH_PX  # 相对默认画布宽的比例
    palette = MATERIAL_COLORS[params.materials[0]]
    floors = params.floors
    margin = int(40 * scale)
    window_w = int(90 * scale)
    cols = _window_cols(params.width_m)
    gap = (width_px - 2 * margin - cols * window_w) // (cols - 1) if cols > 1 else 0

    ys, window_h = _window_rows(floors, height_px, margin)

    windows: list[WindowRect] = []
    for y in ys:
        for c in range(cols):
            x = margin + c * (window_w + gap)
            windows.append(WindowRect(x=x, y=y, w=window_w, h=window_h))

    return FacadeSpec(
        width_px=width_px,
        height_px=height_px,
        floors=floors,
        windows=windows,
        roof=params.roof,
        style=params.style,
        roof_geom=_roof_geom(params),
        cornice=CorniceSpec(has=False, thickness=0, y=None),
        palette=palette,
    )
