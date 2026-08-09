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


def _fake_output_file(tmp_path: Path, name: str) -> Path:
    """Create a real fake output file so mock Replicate returns a valid path."""
    p = tmp_path / name
    p.write_bytes(b"fake-png-bytes")
    return p


@pytest.mark.asyncio
@patch("generation.generators.api.replicate_gen.replicate.run")
async def test_generate_returns_artifact(mock_run, tmp_path: Path):
    # mock Replicate returns a real file path (urlretrieve can copy)
    out = _fake_output_file(tmp_path, "out.png")
    mock_run.return_value = [str(out)]

    # mock urlretrieve: copy source file directly to destination
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=MagicMock())
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
@patch("generation.generators.api.replicate_gen.replicate.run")
async def test_generate_calls_replicate_twice(mock_run, tmp_path: Path):
    out = _fake_output_file(tmp_path, "out.png")
    mock_run.return_value = [str(out)]

    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=MagicMock())
        await gen.generate(_params(), "sid-2", tmp_path, "zh")

    # two SDXL calls (facade + floorplan)
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_generate_without_client_raises(tmp_path: Path):
    # no API key / client -> configuration error
    from generation.generators.api.replicate_gen import ApiGeneratorError

    with pytest.raises(ApiGeneratorError):
        await ApiGenerator(replicate_client=None).generate(_params(), "s", tmp_path, "zh")
