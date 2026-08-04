from generation.generators.simulator.floorplan import (
    ROOM_NAMES_EN,
    ROOM_NAMES_ZH,
    build_floorplan_spec,
)
from generation.params.model import BuildingParams


def _params(**overrides):
    base = dict(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    base.update(overrides)
    return BuildingParams(**base)


def test_floorplan_outer_rect_within_canvas():
    spec = build_floorplan_spec(_params())
    x, y, w, h = spec.outer
    assert x >= 0 and y >= 0
    assert x + w <= spec.width_px
    assert y + h <= spec.height_px
    assert w > 0 and h > 0


def test_floorplan_rooms_zh():
    spec = build_floorplan_spec(_params(), lang="zh")
    texts = [r.text for r in spec.rooms]
    assert texts  # 至少一个房间
    assert all(t in ROOM_NAMES_ZH for t in texts)


def test_floorplan_rooms_en():
    spec = build_floorplan_spec(_params(), lang="en")
    texts = [r.text for r in spec.rooms]
    assert texts  # 至少一个房间
    assert all(t in ROOM_NAMES_EN for t in texts)


def test_floorplan_room_count_scales_with_width():
    spec_small = build_floorplan_spec(_params(width_m=6.0))
    spec_large = build_floorplan_spec(_params(width_m=20.0))
    assert len(spec_large.rooms) >= len(spec_small.rooms)
