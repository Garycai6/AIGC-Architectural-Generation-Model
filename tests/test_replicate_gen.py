# tests/test_replicate_gen.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from generation.generators.api.replicate_gen import ApiGenerator
from generation.generators.base import GenerationArtifact
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


def _make_client(tmp_path: Path):
    """Build a client with mock .run returning [edge-map, real-image] paths.

    Mirrors the real controlnet-sdxl output: list where the LAST item is the
    real generated image (earlier items are ControlNet edge maps).
    """
    edge = tmp_path / "edge.png"
    edge.write_bytes(b"fake-edge")
    real = tmp_path / "real.png"
    real.write_bytes(b"fake-png-bytes")
    client = MagicMock()
    client.run.return_value = [str(edge), str(real)]
    return client, real


@pytest.mark.asyncio
async def test_generate_returns_artifact(tmp_path: Path):
    client, out = _make_client(tmp_path)
    # mock urlretrieve: copy source file directly to destination
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=client)
        art = await gen.generate(_params(), "sid-1", tmp_path, "zh")

    assert isinstance(art, GenerationArtifact)
    assert art.scheme_id == "sid-1"
    assert len(art.images) == 2
    kinds = {img.kind for img in art.images}
    assert kinds == {"facade", "floorplan"}
    # real image files exist (copied by mock urlretrieve)
    for img in art.images:
        path = tmp_path / img.url.rsplit("/", 1)[-1]
        assert path.exists()


@pytest.mark.asyncio
async def test_generate_calls_replicate_twice(tmp_path: Path):
    client, out = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=client)
        await gen.generate(_params(), "sid-2", tmp_path, "zh")

    # two SDXL calls (facade + floorplan), through the injected client
    assert client.run.call_count == 2


@pytest.mark.asyncio
async def test_generate_without_client_raises(tmp_path: Path):
    # no API key / client -> constructor raises configuration error
    from generation.generators.api.replicate_gen import ApiGeneratorError

    with pytest.raises(ApiGeneratorError):
        ApiGenerator(replicate_client=None)
