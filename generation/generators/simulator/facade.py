from pydantic import BaseModel

from generation.params.model import BuildingParams

FLOOR_HEIGHT_M = 3.2  # 与 params.model 一致
MAX_WIDTH_PX = 640
MAX_HEIGHT_PX = 480


class WindowRect(BaseModel):
    x: int
    y: int
    w: int
    h: int
    cross: bool = True


class MaterialPalette(BaseModel):
    main: str
    accent: str
    trim: str


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
    roof: str
    palette: MaterialPalette


def _window_cols(width_px: int) -> int:
    # 按面宽推导窗列数:6-10m 两列,11-20m 三列
    return 2 if width_px < 0.5 * MAX_WIDTH_PX else 3


def _window_row(floor_idx: int, floors: int, window_h: int) -> int:
    # 每层窗在层内垂直居中,层间留缝
    return 40 + floor_idx * (window_h + 60) + 10


def _window_rows(floors: int, height_px: int, margin: int, scale: float) -> list[int]:
    """按层数在画布高度内均分楼层,返回每层窗的 y 坐标(层内垂直居中)。

    保证任意 floors(1-6)下窗口都不超出画布。
    """
    avail_h = height_px - 2 * margin
    floor_h = avail_h // floors
    window_h = max(20, floor_h - 24)
    return [margin + f * floor_h + (floor_h - window_h) // 2 for f in range(floors)]


def build_facade_spec(
    params: BuildingParams, width_px: int = 640, height_px: int = 480
) -> FacadeSpec:
    scale = width_px / MAX_WIDTH_PX  # 相对默认面宽的比例
    palette = MATERIAL_COLORS[params.materials[0]]
    floors = params.floors
    margin = int(40 * scale)
    window_w = int(90 * scale)
    cols = _window_cols(width_px)
    gap = (width_px - 2 * margin - cols * window_w) // (cols - 1) if cols > 1 else 0

    ys = _window_rows(floors, height_px, margin, scale)
    window_h = (ys[1] - ys[0] - 10) if floors > 1 else max(20, (height_px - 2 * margin) - 60)

    windows: list[WindowRect] = []
    for _, y in enumerate(ys):
        for c in range(cols):
            x = margin + c * (window_w + gap)
            windows.append(WindowRect(x=x, y=y, w=window_w, h=window_h))

    return FacadeSpec(
        width_px=width_px,
        height_px=height_px,
        floors=floors,
        windows=windows,
        roof=params.roof,
        palette=palette,
    )
