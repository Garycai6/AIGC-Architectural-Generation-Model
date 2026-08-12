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
    app.state.quota_service = QuotaService(app.state.settings.max_free_quota)

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
