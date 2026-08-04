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


def _shift_hex(hex_color: str, dr: int, dg: int, db: int) -> str:
    """将 #RRGGBB 的 RGB 分量各偏移 delta,裁剪到 [0, 255],返回新 hex。"""
    r = int(hex_color[1:3], 16) + dr
    g = int(hex_color[3:5], 16) + dg
    b = int(hex_color[5:7], 16) + db
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class ModernStyle(StyleConfig):
    window_ratio = (3.0, 1.0)
    window_arch = False

    def cornice(self, width_px: int) -> CorniceSpec:
        return CorniceSpec(has=False, thickness=0, y=None)

    def apply_palette(self, mat: MaterialPalette) -> MaterialPalette:
        # 中性偏冷:主色去饱和,微偏蓝
        return MaterialPalette(
            main=_shift_hex(mat.main, -10, -10, 8), accent=mat.accent, trim=mat.trim
        )

    def build_roof_geom(self, params: BuildingParams) -> RoofGeometry:
        return _roof_geom(params)


class NeoclassicStyle(StyleConfig):
    window_ratio = (0.6, 1.2)
    window_arch = False

    def cornice(self, width_px: int) -> CorniceSpec:
        return CorniceSpec(has=True, thickness=8, y=20)

    def apply_palette(self, mat: MaterialPalette) -> MaterialPalette:
        # 暖灰:主色加灰调,降低饱和度
        return MaterialPalette(
            main=_shift_hex(mat.main, 8, 0, -8), accent=mat.accent, trim=mat.trim
        )

    def build_roof_geom(self, params: BuildingParams) -> RoofGeometry:
        return _roof_geom(params)


class EuropeanStyle(StyleConfig):
    window_ratio = (0.8, 1.2)
    window_arch = True

    def cornice(self, width_px: int) -> CorniceSpec:
        return CorniceSpec(has=True, thickness=5, y=16)

    def apply_palette(self, mat: MaterialPalette) -> MaterialPalette:
        # 暖调:主色偏暖
        return MaterialPalette(
            main=_shift_hex(mat.main, 10, 2, -12), accent=mat.accent, trim=mat.trim
        )

    def build_roof_geom(self, params: BuildingParams) -> RoofGeometry:
        return _roof_geom(params)


class NordicStyle(StyleConfig):
    window_ratio = (1.0, 1.0)
    window_arch = False

    def cornice(self, width_px: int) -> CorniceSpec:
        return CorniceSpec(has=True, thickness=3, y=12)

    def apply_palette(self, mat: MaterialPalette) -> MaterialPalette:
        # 低饱和:主色去饱和偏灰
        return MaterialPalette(
            main=_shift_hex(mat.main, -6, -6, -6), accent=mat.accent, trim=mat.trim
        )

    def build_roof_geom(self, params: BuildingParams) -> RoofGeometry:
        return _roof_geom(params)


STYLE_REGISTRY: dict[str, type[StyleConfig]] = {
    "modern": ModernStyle,
    "neoclassic": NeoclassicStyle,
    "european": EuropeanStyle,
    "nordic": NordicStyle,
}


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
    style = STYLE_REGISTRY[params.style]()
    palette = style.apply_palette(MATERIAL_COLORS[params.materials[0]])
    floors = params.floors
    margin = int(40 * (width_px / MAX_WIDTH_PX))
    ratio = style.window_ratio
    window_w = int(90 * (width_px / MAX_WIDTH_PX))
    # 窗高:风格 ratio 推导,但不超过楼层可用高(保证任意 floors 不越画布)
    ys, row_h = _window_rows(floors, height_px, margin)
    style_h = int(window_w * ratio[1] / ratio[0])
    window_h = max(20, min(style_h, row_h))
    cols = _window_cols(params.width_m)
    gap = (width_px - 2 * margin - cols * window_w) // (cols - 1) if cols > 1 else 0
    windows: list[WindowRect] = []
    for y in ys:
        for c in range(cols):
            x = margin + c * (window_w + gap)
            windows.append(WindowRect(x=x, y=y, w=window_w, h=window_h, arch=style.window_arch))
    return FacadeSpec(
        width_px=width_px,
        height_px=height_px,
        floors=floors,
        windows=windows,
        roof=params.roof,
        style=params.style,
        roof_geom=style.build_roof_geom(params),
        cornice=style.cornice(width_px),
        palette=palette,
    )
