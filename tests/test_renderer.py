from pathlib import Path

import pytest

from generation.generators.base import GenerationArtifact
from generation.generators.simulator import renderer
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


def test_render_facade_png_creates_file(tmp_path: Path):
    from generation.generators.simulator.facade import build_facade_spec

    spec = build_facade_spec(_params())
    out = tmp_path / "facade.png"
    renderer._render_facade_png(spec, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_render_floorplan_png_creates_file(tmp_path: Path):
    from generation.generators.simulator.floorplan import build_floorplan_spec

    spec = build_floorplan_spec(_params())
    out = tmp_path / "floorplan.png"
    renderer._render_floorplan_png(spec, out)
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.asyncio
async def test_render_scheme_returns_artifact(tmp_path: Path):
    art = await renderer.render_scheme(_params(), "abc123", tmp_path, "zh")
    assert isinstance(art, GenerationArtifact)
    assert art.scheme_id == "abc123"
    assert len(art.images) == 2
    kinds = {img.kind for img in art.images}
    assert kinds == {"facade", "floorplan"}
    for img in art.images:
        assert img.url.startswith("/images/abc123/")
        path = tmp_path / img.url.rsplit("/", 1)[-1]
        assert path.exists()


@pytest.mark.asyncio
async def test_render_scheme_respects_lang(tmp_path: Path):
    # 验证 lang 参数真实影响平面图房间标签语言
    from generation.generators.simulator.floorplan import build_floorplan_spec

    params = _params()
    spec_zh = build_floorplan_spec(params, lang="zh")
    spec_en = build_floorplan_spec(params, lang="en")
    assert spec_zh.rooms[0].text in {"厨房", "卧室", "客厅", "卫生间"}
    assert spec_en.rooms[0].text in {"Kitchen", "Bedroom", "Living", "Bath"}
    assert {r.text for r in spec_zh.rooms} != {r.text for r in spec_en.rooms}

    # render_scheme 接受两种 lang 不崩溃,产物完整
    art_zh = await renderer.render_scheme(params, "a", tmp_path, "zh")
    art_en = await renderer.render_scheme(params, "b", tmp_path, "en")
    assert len(art_zh.images) == 2
    assert len(art_en.images) == 2


def test_render_roof_kinds_produce_different_png(tmp_path: Path):
    from generation.generators.simulator.facade import build_facade_spec

    files = {}
    for roof in ("flat", "pitched", "hipped"):
        spec = build_facade_spec(_params(roof=roof))
        out = tmp_path / f"{roof}.png"
        renderer._render_facade_png(spec, out)
        files[roof] = out
        assert out.exists()
        assert out.stat().st_size > 0
    # 三种屋顶 PNG 不应完全相同(视觉差异化生效)
    flat_bytes = files["flat"].read_bytes()
    pitched_bytes = files["pitched"].read_bytes()
    hipped_bytes = files["hipped"].read_bytes()
    assert flat_bytes != pitched_bytes
    assert pitched_bytes != hipped_bytes


def test_render_styles_produce_different_png(tmp_path: Path):
    from generation.generators.simulator.facade import build_facade_spec

    files = {}
    for style in ("modern", "neoclassic", "european", "nordic"):
        spec = build_facade_spec(_params(style=style))
        out = tmp_path / f"{style}.png"
        renderer._render_facade_png(spec, out)
        files[style] = out
        assert out.exists()
        assert out.stat().st_size > 0
    # 四种风格 PNG 不应完全相同
    b1 = files["modern"].read_bytes()
    assert b1 != files["neoclassic"].read_bytes()
    assert b1 != files["european"].read_bytes()
    assert b1 != files["nordic"].read_bytes()
