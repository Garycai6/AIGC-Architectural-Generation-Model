from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from generation.generators.api.fal_gen import FalGenerator, FalGeneratorError
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
    """Build a fal_client mock: upload_file returns a URL, submit_async
    returns a handle whose get() resolves to images[0].url."""
    real = tmp_path / "real.png"
    real.write_bytes(b"fake-fal-png-bytes")
    handle = MagicMock()
    handle.get = AsyncMock(return_value={"images": [{"url": str(real)}]})
    client = MagicMock()
    client.upload_file = MagicMock(return_value="https://storage.fal.ai/upload/xyz.png")
    client.submit_async = AsyncMock(return_value=handle)
    return client, real


@pytest.mark.asyncio
async def test_generate_returns_artifact(tmp_path: Path):
    client, _ = _make_client(tmp_path)
    with patch(
        "generation.generators.api.fal_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = FalGenerator(fal_client=client)
        art = await gen.generate(_params(), "sid-fal-1", tmp_path, "zh")
    assert art.scheme_id == "sid-fal-1"
    assert [img.kind for img in art.images] == ["facade", "floorplan"]
    assert (tmp_path / "facade.png").read_bytes() == b"fake-fal-png-bytes"
    assert not (tmp_path / "facade_line.png").exists()  # 条件图已清理


@pytest.mark.asyncio
async def test_uploads_lineart_and_passes_arguments(tmp_path: Path):
    client, _ = _make_client(tmp_path)
    with patch(
        "generation.generators.api.fal_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = FalGenerator(fal_client=client)
        await gen.generate(_params(), "sid-fal-2", tmp_path, "zh")
    client.upload_file.assert_called_once()
    kwargs = client.submit_async.call_args.kwargs
    assert kwargs["arguments"]["control_image_url"] == "https://storage.fal.ai/upload/xyz.png"
    assert kwargs["arguments"]["controlnet_conditioning_scale"] == 0.5
    assert kwargs["arguments"]["num_inference_steps"] == 30
    assert kwargs["arguments"]["guidance_scale"] == 7.5
    assert kwargs["arguments"]["seed"] == 42
    assert kwargs["arguments"]["image_size"] == {"width": 1024, "height": 1024}
    assert kwargs["arguments"]["prompt"]  # build_prompt 构造的非空 prompt
    assert kwargs["timeout"] == 300


def test_missing_client_raises():
    with pytest.raises(FalGeneratorError):
        FalGenerator()
