from pathlib import Path

import pytest

from generation.generators.base import GenerationArtifact, Generator, ImageRef
from generation.params.model import BuildingParams


def test_image_ref_model():
    ref = ImageRef(kind="facade", url="/images/abc/facade.png")
    assert ref.kind == "facade"
    assert ref.url.endswith("facade.png")


def test_generation_artifact_model():
    art = GenerationArtifact(
        scheme_id="abc",
        images=[ImageRef(kind="facade", url="/images/abc/facade.png")],
    )
    assert art.scheme_id == "abc"
    assert len(art.images) == 1


class DummyGenerator:
    """实现 Generator 协议的桩,仅用于协议可用性检查。"""

    async def generate(self, params, scheme_id, out_dir, lang="zh"):
        return GenerationArtifact(scheme_id=scheme_id, images=[])


@pytest.mark.asyncio
async def test_generator_protocol_dummy():
    gen: Generator = DummyGenerator()
    params = BuildingParams(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    art = await gen.generate(params, "abc", Path("."), "zh")
    assert isinstance(art, GenerationArtifact)
    assert art.scheme_id == "abc"
