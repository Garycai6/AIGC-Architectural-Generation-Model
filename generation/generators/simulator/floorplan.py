from pydantic import BaseModel

from generation.params.model import BuildingParams

ROOM_NAMES_ZH = ["厨房", "卧室", "客厅", "卫生间"]
ROOM_NAMES_EN = ["Kitchen", "Bedroom", "Living", "Bath"]


class RoomLabel(BaseModel):
    text: str
    x: int
    y: int
    w: int
    h: int


class FloorplanSpec(BaseModel):
    width_px: int
    height_px: int
    outer: tuple[int, int, int, int]  # (x, y, w, h) 外墙矩形
    rooms: list[RoomLabel]


def build_floorplan_spec(
    params: BuildingParams,
    lang: str = "zh",
    width_px: int = 480,
    height_px: int = 360,
) -> FloorplanSpec:
    names = ROOM_NAMES_ZH if lang == "zh" else ROOM_NAMES_EN
    margin = 30
    avail_w = width_px - 2 * margin
    avail_h = height_px - 2 * margin
    # 按宽深比缩放外墙矩形
    ratio = params.depth_m / params.width_m if params.width_m else 0.8
    if ratio > avail_h / avail_w:
        h = avail_h
        w = int(h * params.width_m / params.depth_m)
    else:
        w = avail_w
        h = int(w * ratio)
    outer = (margin, margin, w, h)

    # 按宽度切 2-3 列,按层数切 2 行,形成房间网格
    cols = 2 if params.width_m < 12 else 3
    rows = 2
    cell_w = w // cols
    cell_h = h // rows
    rooms: list[RoomLabel] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            name = names[idx % len(names)]
            rooms.append(
                RoomLabel(
                    text=name,
                    x=margin + c * cell_w,
                    y=margin + r * cell_h,
                    w=cell_w,
                    h=cell_h,
                )
            )
            idx += 1
    return FloorplanSpec(
        width_px=width_px,
        height_px=height_px,
        outer=outer,
        rooms=rooms,
    )
