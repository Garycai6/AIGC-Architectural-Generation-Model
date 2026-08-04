from generation.generators.simulator.facade import (
    MATERIAL_COLORS,
    CorniceSpec,
    RoofGeometry,
    StyleConfig,
    _roof_geom,
    build_facade_spec,
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


def test_build_facade_spec_basic():
    spec = build_facade_spec(_params(floors=3))
    assert spec.width_px == 640
    assert spec.height_px == 480
    assert spec.floors == 3
    assert len(spec.windows) > 0
    for w in spec.windows:
        assert 0 <= w.x < spec.width_px
        assert 0 <= w.y < spec.height_px
        assert w.w > 0 and w.h > 0


def test_build_facade_spec_window_count_scales_with_floors():
    spec1 = build_facade_spec(_params(floors=1))
    spec3 = build_facade_spec(_params(floors=3))
    # 每层都有窗;总窗数随层数单调不减
    assert len(spec3.windows) >= len(spec1.windows) + 1


def test_roof_style_variation():
    flat = build_facade_spec(_params(roof="flat"))
    pitched = build_facade_spec(_params(roof="pitched"))
    assert flat.roof == "flat"
    assert pitched.roof == "pitched"


def test_material_palette_keys():
    assert set(MATERIAL_COLORS.keys()) == {"glass", "stone", "brick", "wood"}
    for pal in MATERIAL_COLORS.values():
        assert pal.main.startswith("#")
        assert pal.accent.startswith("#")
        assert pal.trim.startswith("#")


def test_window_cols_by_building_width():
    narrow = build_facade_spec(_params(width_m=8.0, floors=1))
    wide = build_facade_spec(_params(width_m=15.0, floors=1))
    narrow_cols = len([w for w in narrow.windows if w.y == narrow.windows[0].y])
    wide_cols = len([w for w in wide.windows if w.y == wide.windows[0].y])
    assert narrow_cols == 2
    assert wide_cols == 3


def test_windows_within_canvas_floors6():
    spec = build_facade_spec(_params(floors=6))
    for w in spec.windows:
        assert 0 <= w.x and w.x + w.w <= spec.width_px
        assert 0 <= w.y and w.y + w.h <= spec.height_px


def test_facade_spec_has_visual_fields():
    spec = build_facade_spec(_params(roof="flat"))
    # 升级后的字段存在
    assert spec.style == "modern"
    assert isinstance(spec.roof_geom, RoofGeometry)
    assert spec.roof_geom.kind == "flat"
    assert isinstance(spec.cornice, CorniceSpec)
    # 兼容:roof 字段保留
    assert spec.roof == "flat"


def test_roof_geom_kinds():
    flat = _roof_geom(_params(roof="flat"))
    pitched = _roof_geom(_params(roof="pitched"))
    hipped = _roof_geom(_params(roof="hipped"))
    assert flat.kind == "flat"
    assert flat.ridge_y is None
    assert pitched.kind == "pitched"
    assert pitched.ridge_y is not None
    assert hipped.kind == "hipped"
    assert hipped.ridge_y is not None


def test_style_config_abstract():
    # StyleConfig 是抽象基类,不能直接实例化
    import pytest

    with pytest.raises(TypeError):
        StyleConfig()
