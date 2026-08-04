import pytest

from generation.generators.simulator.perspective import (
    project_iso,
    project_rect,
)


def test_project_iso_zero_depth_identity():
    p = project_iso(100.0, 200.0, depth=0.0)
    assert p.x == pytest.approx(100.0)
    assert p.y == pytest.approx(200.0)


def test_project_iso_positive_depth_offsets_x_and_y():
    p = project_iso(100.0, 200.0, depth=50.0, depth_scale=0.5)
    # 深度向右、向下偏移,形成等轴感
    assert p.x > 100.0
    assert p.y > 200.0


def test_project_rect_four_corners():
    pts = project_rect((100, 200, 40, 60), depth=0.0)
    assert len(pts) == 4
    # 逆时针:左上、右上、右下、左下
    assert pts[0].x == 100 and pts[0].y == 200
    assert pts[1].x == 140 and pts[1].y == 200
    assert pts[2].x == 140 and pts[2].y == 260
    assert pts[3].x == 100 and pts[3].y == 260
