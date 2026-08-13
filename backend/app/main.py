import pathlib

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.generate import router as generate_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.quota import QuotaService


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="ArchGen API", version="0.1.0")
    app.state.settings = settings or get_settings()
    if app.state.settings.quota_storage_path:
        # quota 持久化文件父目录必须先于 QuotaService 构造创建(构造时加载文件)
        pathlib.Path(app.state.settings.quota_storage_path).parent.mkdir(
            parents=True, exist_ok=True
        )
    app.state.quota_service = QuotaService(
        app.state.settings.max_free_quota,
        storage_path=(
            pathlib.Path(app.state.settings.quota_storage_path)
            if app.state.settings.quota_storage_path
            else None
        ),
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(generate_router, prefix="/api/v1")

    cache_dir = pathlib.Path(app.state.settings.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(cache_dir)), name="images")
    return app


def run() -> None:
    """uvicorn 入口(供 `archgen-api` 脚本使用)。"""
    uvicorn.run("backend.app.main:create_app", factory=True, host="0.0.0.0", port=8000)
