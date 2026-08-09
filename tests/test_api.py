import tempfile

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from generation.generators.base import GenerationArtifact, ImageRef


def _make_app(cache_dir: str | None = None):
    # 显式传参,避免从 .env / 环境变量读取,保证测试确定性
    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=cache_dir or tempfile.mkdtemp(),
    )
    return create_app(settings)


def test_health():
    client = TestClient(_make_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_generate_skeleton(tmp_path):
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=str(tmp_path),
    )
    client = TestClient(create_app(settings))
    resp = client.post(
        "/api/v1/generate",
        json={
            "params": {
                "style": "modern",
                "floors": 3,
                "width_m": 10.0,
                "depth_m": 8.0,
                "materials": ["glass"],
                "roof": "flat",
                "environment": "suburb",
            },
            "lang": "zh",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheme_id"]
    assert len(body["images"]) == 2
    assert "设计" in body["description"]  # 空 key → 占位文案分支
    # 静态文件可访问
    for url in body["images"]:
        img_resp = client.get(url)
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"] == "image/png"


def test_generate_invalid_params():
    client = TestClient(_make_app())
    resp = client.post(
        "/api/v1/generate",
        json={
            "params": {
                "style": "baroque",
                "floors": 3,
                "width_m": 10.0,
                "depth_m": 8.0,
                "materials": ["glass"],
                "roof": "flat",
                "environment": "suburb",
            },
            "lang": "zh",
        },
    )
    assert resp.status_code == 422


def test_generate_defaults_to_simulator(tmp_path):
    # 不显式传 image_provider → Settings 默认 "simulator",验证默认回退路径
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        max_free_quota=5,
        cache_dir=str(tmp_path),
    )
    assert settings.image_provider == "simulator"  # 默认值必须走模拟器
    client = TestClient(create_app(settings))
    resp = client.post(
        "/api/v1/generate",
        json={
            "params": {
                "style": "modern",
                "floors": 3,
                "width_m": 10.0,
                "depth_m": 8.0,
                "materials": ["glass"],
                "roof": "flat",
                "environment": "suburb",
            },
            "lang": "zh",
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["images"]) == 2


def test_generate_uses_apigenerator_when_replicate(tmp_path):
    from unittest.mock import AsyncMock, patch

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
        cache_dir=str(tmp_path),
        replicate_api_token="test-token",
    )
    with patch("backend.app.api.generate.ApiGenerator") as mock_cls:
        mock_gen = mock_cls.return_value
        mock_gen.generate = AsyncMock(
            return_value=GenerationArtifact(
                scheme_id="s1",
                images=[
                    ImageRef(kind="facade", url="/images/s1/facade.png"),
                    ImageRef(kind="floorplan", url="/images/s1/floorplan.png"),
                ],
            )
        )
        client = TestClient(create_app(settings))
        resp = client.post(
            "/api/v1/generate",
            json={
                "params": {
                    "style": "modern",
                    "floors": 3,
                    "width_m": 10.0,
                    "depth_m": 8.0,
                    "materials": ["glass"],
                    "roof": "flat",
                    "environment": "suburb",
                },
                "lang": "zh",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["images"]) == 2
        mock_cls.assert_called_once()
