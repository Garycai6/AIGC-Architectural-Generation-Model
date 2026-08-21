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
    assert body["remaining_quota"] == 5  # 无头请求报满额(max_free_quota=5)
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
    # 显式传 image_provider=simulator,不依赖 .env(避免被真调配置污染)
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=str(tmp_path),
    )
    assert settings.image_provider == "simulator"  # simulator 路径正常
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


def test_generate_replicate_injects_lora_and_model(tmp_path):
    from unittest.mock import AsyncMock, patch

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
        cache_dir=str(tmp_path),
        replicate_api_token="test-token",
        sdxl_model="fermatresearch/sdxl-controlnet-lora:latest",
        lora_weights_dir="https://cdn.example.com/lora",
        lora_weights_url="",  # 显式清空,避免从 .env 读入
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
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["model"] == "fermatresearch/sdxl-controlnet-lora:latest"
        assert kwargs["lora_urls"] == {
            "modern": "https://cdn.example.com/lora/modern.tar",
            "neoclassic": "https://cdn.example.com/lora/neoclassic.tar",
            "european": "https://cdn.example.com/lora/european.tar",
            "nordic": "https://cdn.example.com/lora/nordic.tar",
        }


def test_generate_replicate_single_lora_url(tmp_path):
    """lora_weights_url(单 URL,如 Replicate 官方训练)→ 所有风格共用同一权重 URL。"""
    from unittest.mock import AsyncMock, patch

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
        cache_dir=str(tmp_path),
        replicate_api_token="test-token",
        sdxl_model="fermatresearch/sdxl-controlnet-lora:latest",
        lora_weights_dir="",  # 清空,避免 .env 干扰
        lora_weights_url="https://replicate.delivery/xxx/trained_model.tar",
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
        kwargs = mock_cls.call_args.kwargs
        assert kwargs["lora_urls"] == {
            "modern": "https://replicate.delivery/xxx/trained_model.tar",
            "neoclassic": "https://replicate.delivery/xxx/trained_model.tar",
            "european": "https://replicate.delivery/xxx/trained_model.tar",
            "nordic": "https://replicate.delivery/xxx/trained_model.tar",
        }


def _quota_payload():
    return {
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
    }


def test_generate_quota_exhausted_after_max(tmp_path):
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=3,
        cache_dir=str(tmp_path),
    )
    client = TestClient(create_app(settings))
    headers = {"X-Visitor-Id": "visitor-1"}
    for i in range(3):
        resp = client.post("/api/v1/generate", json=_quota_payload(), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["remaining_quota"] == 2 - i  # 2, 1, 0
    resp = client.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp.status_code == 429
    assert resp.json() == {"detail": "今日免费额度已用完"}


def test_generate_quota_isolated_per_visitor(tmp_path):
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=1,
        cache_dir=str(tmp_path),
    )
    client = TestClient(create_app(settings))
    # visitor-a 用满 1 次
    resp = client.post(
        "/api/v1/generate", json=_quota_payload(), headers={"X-Visitor-Id": "visitor-a"}
    )
    assert resp.status_code == 200
    assert resp.json()["remaining_quota"] == 0  # max=1,consumed its only slot
    # visitor-a 再次请求 → 429
    resp = client.post(
        "/api/v1/generate", json=_quota_payload(), headers={"X-Visitor-Id": "visitor-a"}
    )
    assert resp.status_code == 429
    # visitor-b 独立计数 → 200
    resp = client.post(
        "/api/v1/generate", json=_quota_payload(), headers={"X-Visitor-Id": "visitor-b"}
    )
    assert resp.status_code == 200
    assert resp.json()["remaining_quota"] == 0  # max=1,consumed its only slot


def test_generate_quota_persists_across_app_restart(tmp_path):
    from backend.app.core.config import Settings

    storage = tmp_path / "quota.json"
    settings1 = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=2,
        cache_dir=str(tmp_path / "cache1"),
        quota_storage_path=str(storage),
    )
    client1 = TestClient(create_app(settings1))
    headers = {"X-Visitor-Id": "visitor-1"}
    resp1 = client1.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["remaining_quota"] == 1

    # 模拟重启:新的 app 实例、同一 storage_path
    settings2 = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=2,
        cache_dir=str(tmp_path / "cache2"),
        quota_storage_path=str(storage),
    )
    client2 = TestClient(create_app(settings2))
    resp2 = client2.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["remaining_quota"] == 0  # 已用 1,剩 1,本次消费后 0
    resp3 = client2.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp3.status_code == 429  # 跨重启额度保留,继续计数


def test_generate_uses_falgenerator_when_fal(tmp_path):
    from unittest.mock import AsyncMock, patch

    from generation.generators.api.fal_gen import FAL_MODEL

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="fal",
        max_free_quota=5,
        cache_dir=str(tmp_path),
        fal_api_key="test-fal-key",
    )
    with patch("backend.app.api.generate.FalGenerator") as mock_cls:
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
            json=_quota_payload(),
            headers={"X-Visitor-Id": "fal-test"},
        )
        assert resp.status_code == 200
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["model"] == FAL_MODEL


def test_generate_fal_missing_token_returns_500(tmp_path):
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="fal",
        max_free_quota=5,
        cache_dir=str(tmp_path),
    )
    client = TestClient(create_app(settings))
    resp = client.post(
        "/api/v1/generate",
        json=_quota_payload(),
        headers={"X-Visitor-Id": "fal-test"},
    )
    assert resp.status_code == 500
