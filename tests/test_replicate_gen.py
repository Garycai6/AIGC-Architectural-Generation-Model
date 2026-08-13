# tests/test_replicate_gen.py
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
    """Build a client with mock .async_run returning [edge-map, real-image] paths.

    Mirrors the real controlnet-sdxl output: list where the LAST item is the
    real generated image (earlier items are ControlNet edge maps).
    """
    edge = tmp_path / "edge.png"
    edge.write_bytes(b"fake-edge")
    real = tmp_path / "real.png"
    real.write_bytes(b"fake-png-bytes")
    client = MagicMock()
    client.async_run = AsyncMock(return_value=[str(edge), str(real)])
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
async def test_generate_calls_replicate_once(tmp_path: Path):
    """Facade goes through real SDXL; floorplan stays simulator line-art (no
    second SDXL call) — verified 2026-08-05 that SDXL cannot produce correct
    floor plans."""
    client, real = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=client)
        await gen.generate(_params(), "sid-2", tmp_path, "zh")

    # one SDXL call (facade only), through the injected client
    assert client.async_run.call_count == 1


@pytest.mark.asyncio
async def test_generate_without_client_raises(tmp_path: Path):
    # no API key / client -> constructor raises configuration error
    from generation.generators.api.replicate_gen import ApiGeneratorError

    with pytest.raises(ApiGeneratorError):
        ApiGenerator(replicate_client=None)


@pytest.mark.asyncio
async def test_generate_injects_lora_when_configured(tmp_path: Path):
    """配置了 lora_urls 且风格命中 → client.async_run 收到 lora_weights=<url>。"""
    client, real = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(
            replicate_client=client,
            lora_urls={"modern": "https://cdn.example.com/lora/modern.tar"},
        )
        await gen.generate(_params(style="modern"), "sid-l1", tmp_path, "zh")

    kwargs = client.async_run.call_args.kwargs
    assert kwargs["input"]["lora_weights"] == "https://cdn.example.com/lora/modern.tar"


@pytest.mark.asyncio
async def test_generate_no_lora_when_unconfigured(tmp_path: Path):
    """未配置 lora_urls → client.async_run 不收 lora_weights(向后兼容)。"""
    client, real = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=client)
        await gen.generate(_params(), "sid-l2", tmp_path, "zh")

    assert "lora_weights" not in client.async_run.call_args.kwargs["input"]


@pytest.mark.asyncio
async def test_generate_lora_missing_style_falls_back(tmp_path: Path):
    """lora_urls 配置了但没有该风格 → 不注入 lora_weights,不报错(降级)。"""
    client, real = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(
            replicate_client=client,
            lora_urls={"modern": "https://cdn.example.com/lora/modern.tar"},
        )
        await gen.generate(_params(style="nordic"), "sid-l3", tmp_path, "zh")

    assert "lora_weights" not in client.async_run.call_args.kwargs["input"]


def test_settings_lora_fields_default_empty():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=".tmp-test",
    )
    assert settings.sdxl_model == ""
    assert settings.lora_weights_dir == ""


def test_settings_lora_fields_can_be_set():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
        cache_dir=".tmp-test",
        replicate_api_token="tok",
        sdxl_model="fermatresearch/sdxl-controlnet-lora:latest",
        lora_weights_dir="https://cdn.example.com/lora",
    )
    assert settings.sdxl_model == "fermatresearch/sdxl-controlnet-lora:latest"
    assert settings.lora_weights_dir == "https://cdn.example.com/lora"


def test_settings_quota_storage_path_default_empty():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=".tmp-test",
    )
    assert settings.quota_storage_path == ""


def test_settings_quota_storage_path_can_be_set():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=".tmp-test",
        quota_storage_path=".cache/archgen/quota.json",
    )
    assert settings.quota_storage_path == ".cache/archgen/quota.json"


@pytest.mark.asyncio
async def test_generate_async_run_waits_300(tmp_path: Path):
    """异步调用收到 wait=300(解除 60s read timeout)。"""
    client, real = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=client)
        await gen.generate(_params(), "sid-w1", tmp_path, "zh")

    kwargs = client.async_run.call_args.kwargs
    assert kwargs["wait"] == 300
