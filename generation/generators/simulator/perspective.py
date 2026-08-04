from pydantic import BaseModel


class Point(BaseModel):
    x: float
    y: float


def project_iso(x: float, y: float, depth: float, depth_scale: float = 0.5) -> Point:
    """等轴投影:正立面点叠加深度,向右下方偏移形成 3/4 视角。"""
    return Point(x=x + depth * depth_scale, y=y + depth * depth_scale)


def project_rect(
    rect: tuple[float, float, float, float], depth: float
) -> tuple[Point, Point, Point, Point]:
    """将正立面矩形 (x, y, w, h) 投影为四角点(逆时针)。"""
    x, y, w, h = rect
    return (
        project_iso(x, y, depth),
        project_iso(x + w, y, depth),
        project_iso(x + w, y + h, depth),
        project_iso(x, y + h, depth),
    )
