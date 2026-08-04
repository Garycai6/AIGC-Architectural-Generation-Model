from pathlib import Path

import pytest

from generation.generators import SimulatorGenerator
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


@pytest.mark.asyncio
async def test_simulator_generator_generate(tmp_path: Path):
    gen = SimulatorGenerator()
    art = await gen.generate(_params(), "sid-1", tmp_path, "zh")
    assert art.scheme_id == "sid-1"
    assert len(art.images) == 2
    for img in art.images:
        assert (tmp_path / img.url.rsplit("/", 1)[-1]).exists()


@pytest.mark.asyncio
async def test_simulator_generator_default_lang(tmp_path: Path):
    gen = SimulatorGenerator()
    art = await gen.generate(_params(), "sid-2", tmp_path)
    assert len(art.images) == 2
