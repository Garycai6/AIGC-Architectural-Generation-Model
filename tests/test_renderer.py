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
    art_zh = await renderer.render_scheme(_params(), "a", tmp_path, "zh")
    art_en = await renderer.render_scheme(_params(), "b", tmp_path, "en")
    assert len(art_zh.images) == 2
    assert len(art_en.images) == 2
