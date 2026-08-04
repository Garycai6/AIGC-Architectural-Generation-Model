"""模拟器渲染器——将立面/平面线稿落盘为 PNG,暴露异步入口。"""

import asyncio
import pathlib
from typing import Literal

from PIL import Image, ImageDraw

from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.facade import FacadeSpec, build_facade_spec
from generation.generators.simulator.floorplan import FloorplanSpec, build_floorplan_spec
from generation.generators.simulator.perspective import project_rect
from generation.params.model import BuildingParams

FACADE_FILE = "facade.png"
FLOORPLAN_FILE = "floorplan.png"
FACADE_OUTPUT_PX = (640, 480)
FLOORPLAN_OUTPUT_PX = (480, 360)


def _draw_facade_rect(draw: ImageDraw.ImageDraw, spec: FacadeSpec) -> None:
    """在画布上绘制正立面:体量轮廓、分层线、开窗网格。

    保留供 future「正面视角(front view-angle)」渲染路径使用;当前
    _render_facade_png 走 _draw_facade_perspective(3/4 透视)。
    """
    x0, y0 = 30, 30
    x1 = spec.width_px - 30
    y1 = spec.height_px - 30
    floor_h = (y1 - y0) // spec.floors
    draw.rectangle(
        [x0, y0, x1, y1],
        fill=spec.palette.main,
        outline=spec.palette.trim,
        width=3,
    )
    for f in range(1, spec.floors):
        fy = y0 + f * floor_h
        draw.line([x0, fy, x1, fy], fill=spec.palette.trim, width=2)
    for w in spec.windows:
        draw.rectangle(
            [w.x + x0, w.y + y0, w.x + w.w + x0, w.y + w.h + y0],
            fill=spec.palette.accent,
            outline=spec.palette.trim,
            width=2,
        )
        if w.cross:
            cx = w.x + x0 + w.w // 2
            cy = w.y + y0 + w.h // 2
            draw.line(
                [cx, w.y + y0, cx, w.y + w.h + y0],
                fill=spec.palette.trim,
                width=1,
            )
            draw.line(
                [w.x + x0, cy, w.x + w.w + x0, cy],
                fill=spec.palette.trim,
                width=1,
            )


def _draw_facade_perspective(draw: ImageDraw.ImageDraw, spec: FacadeSpec) -> None:
    """绘制 3/4 透视:正立面投影 + 侧壁与顶面的体量感。"""
    x0, y0 = 30, 30
    x1 = spec.width_px - 30
    y1 = spec.height_px - 30
    depth = 50  # 深度偏移 50*0.5=25px,保证顶面/侧壁不出画布(640×480)
    # 正立面(已投影,深度 0 时与立面一致)
    front = project_rect((x0, y0, x1 - x0, y1 - y0), depth=0)
    # 侧壁:右边界向纵深偏移,形成顶面/侧壁
    back = project_rect((x0, y0, x1 - x0, y1 - y0), depth=depth)
    pts_front = [(p.x, p.y) for p in front]
    draw.polygon(pts_front, fill=spec.palette.main, outline=spec.palette.trim)
    # 顶面:正立面顶边 → 侧壁顶边
    draw.polygon(
        [
            (front[0].x, front[0].y),
            (front[1].x, front[1].y),
            (back[1].x, back[1].y),
            (back[0].x, back[0].y),
        ],
        fill=spec.palette.accent,
        outline=spec.palette.trim,
    )
    # 侧壁(右):正立面右边 → 侧壁右边
    draw.polygon(
        [
            (front[1].x, front[1].y),
            (front[2].x, front[2].y),
            (back[2].x, back[2].y),
            (back[1].x, back[1].y),
        ],
        fill=spec.palette.main,
        outline=spec.palette.trim,
    )
    # 窗在正立面(投影深度 0;project_iso depth=0 为恒等变换,
    # 故下方交叉线可用未投影坐标,与 project_rect 输出一致)
    for w in spec.windows:
        wp = project_rect((w.x + x0, w.y + y0, w.w, w.h), depth=0)
        draw.polygon(
            [(p.x, p.y) for p in wp],
            fill=spec.palette.accent,
            outline=spec.palette.trim,
            width=2,
        )
        if w.cross:
            cx = w.x + x0 + w.w // 2
            cy = w.y + y0 + w.h // 2
            draw.line(
                [cx, w.y + y0, cx, w.y + w.h + y0],
                fill=spec.palette.trim,
                width=1,
            )
            draw.line(
                [w.x + x0, cy, w.x + w.w + x0, cy],
                fill=spec.palette.trim,
                width=1,
            )


def _render_facade_png(spec: FacadeSpec, out_path: object) -> None:
    """将 FacadeSpec 渲染为 3/4 透视 PNG。"""
    img = Image.new("RGB", FACADE_OUTPUT_PX, "#ffffff")
    draw = ImageDraw.Draw(img)
    _draw_facade_perspective(draw, spec)
    img.save(str(out_path))


def _render_floorplan_png(spec: FloorplanSpec, out_path: object) -> None:
    """将 FloorplanSpec 渲染为平面示意 PNG。"""
    img = Image.new("RGB", FLOORPLAN_OUTPUT_PX, "#ffffff")
    draw = ImageDraw.Draw(img)
    x, y, w, h = spec.outer
    draw.rectangle([x, y, x + w, y + h], outline="#333333", width=3)
    for room in spec.rooms:
        draw.rectangle(
            [room.x, room.y, room.x + room.w, room.y + room.h],
            outline="#999999",
            width=1,
        )
        draw.text((room.x + 8, room.y + 8), room.text, fill="#333333")
    img.save(str(out_path))


def _render_sync(
    params: BuildingParams,
    scheme_id: str,
    out_dir: object,
    lang: str,
) -> GenerationArtifact:
    """同步绘制 facade.png 与 floorplan.png,打包为 GenerationArtifact。"""
    out = pathlib.Path(out_dir)
    facade = build_facade_spec(params)
    _render_facade_png(facade, out / FACADE_FILE)
    floorplan = build_floorplan_spec(params, lang=lang)
    _render_floorplan_png(floorplan, out / FLOORPLAN_FILE)
    return GenerationArtifact(
        scheme_id=scheme_id,
        images=[
            ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
            ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
        ],
    )


async def render_scheme(
    params: BuildingParams,
    scheme_id: str,
    out_dir: object,
    lang: Literal["en", "zh"] = "zh",
) -> GenerationArtifact:
    """模拟器渲染入口——同步绘制在线程池,避免阻塞事件循环。"""
    return await asyncio.to_thread(_render_sync, params, scheme_id, out_dir, lang)
