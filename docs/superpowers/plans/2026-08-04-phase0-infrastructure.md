# 阶段 0:基础设施与仓库骨架 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立项目 Monorepo 骨架:包管理、目录结构、BuildingParams 校验、DeepSeek 客户端、FastAPI 空壳、React 空壳、CI,使本机能跑通前后端空壳并冒烟调用 DeepSeek/Replicate。

**Architecture:** Python 后端(FastAPI)为项目核心,`generation/` 包承载参数→条件束→生成的核心逻辑;前端 React 独立目录;两者通过 HTTP API 交互。验证期推理走外部 API(Replicate/Fal),本机零 GPU。

**Tech Stack:** uv、Python 3.11、FastAPI、pydantic v2、pytest、ruff;前端 React + Vite + TypeScript + Tailwind。

## Global Constraints

- Python >= 3.11(本机 3.11.15)
- 包管理用 `uv`(本机 0.11.32),不用 pip 直接装
- 前端语言 React + Vite + TypeScript;样式 Tailwind
- 所有敏感配置走环境变量,`.env` 不入库(见 `.gitignore`);只提交 `.env.example`
- 双语文案统一放 `frontend/src/i18n/{en,zh}.json`,硬编码散落的中文字符串视为缺陷
- API 密钥一律从环境变量读取,代码中不得出现明文密钥
- ruff 格式与 lint 必须通过;pytest 全绿才算任务完成
- 提交信息用 `feat:` / `fix:` / `docs:` 前缀

---

### Task 1: Monorepo 骨架与工具链

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `Makefile`
- Create: `README.md`

**Interfaces:**
- Produces: `pyproject.toml` 中定义的 `gen-backend` / `gen-gpu` / `gen-dev` 三个 optional-dependency 组,以及 `[project.scripts]` 中的 `archgen-api` 入口

- [ ] **Step 1: 创建 `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
dist/
build/
*.egg-info/

# Node
node_modules/
dist/
.vite/

# 环境与密钥
.env
*.pem

# 数据与模型(不入库)
data/raw/
data/processed/
data/captions/
weights/
checkpoints/
*.safetensors
*.bin

# 测试与工具
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
wandb/

# IDE
.idea/
.vscode/
```

- [ ] **Step 2: 创建 `pyproject.toml`**

```toml
[project]
name = "archgen"
version = "0.1.0"
description = "建筑 AIGC 生成模型 - 参数驱动的建筑方案生成 SaaS"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "openai>=1.40",          # DeepSeek 兼容 OpenAI SDK
    "replicate>=1.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
    "httpx>=0.27",           # FastAPI TestClient 依赖
]
gpu = [
    "torch>=2.2",
    "diffusers>=0.29",
    "accelerate>=0.33",
    "peft>=0.12",
]

[project.scripts]
archgen-api = "backend.app.main:run"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["backend", "generation", "data", "training"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: 创建 `.env.example`**

```bash
# DeepSeek API
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 图片生成(验证期)
REPLICATE_API_TOKEN=
# FAL_KEY=

# 后端
ARCHGEN_IMAGE_PROVIDER=replicate        # replicate | fal
ARCHGEN_CACHE_DIR=.cache/archgen
ARCHGEN_MAX_FREE_QUOTA=5
```

- [ ] **Step 4: 创建 `Makefile`**

```makefile
.PHONY: setup test lint run-frontend run-backend

setup:
	uv sync --extra dev
	cd frontend && npm install

test:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .

run-backend:
	uv run archgen-api

run-frontend:
	cd frontend && npm run dev
```

- [ ] **Step 5: 创建 `README.md`**

```markdown
# 建筑 AIGC 生成模型 (ArchGen)

通过 Stable Diffusion/Transformer 微调,输入建筑参数自动生成建筑方案(效果图+平面图)的 SaaS 产品。

## 开发

```bash
make setup    # 安装依赖(uv sync + npm install)
make test     # 跑 pytest
make lint     # ruff 检查
```

详见 `docs/superpowers/plans/` 下的实施计划。
```

- [ ] **Step 6: 初始化 uv 环境并验证**

Run:
```bash
uv sync --extra dev
```
Expected: `.venv` 创建成功,依赖安装无报错。

Run:
```bash
uv run python -c "import fastapi, pydantic; print('OK', fastapi.__version__, pydantic.__version__)"
```
Expected: 打印 `OK <版本>`。

- [ ] **Step 7: 提交**

```bash
git add pyproject.toml .gitignore .env.example Makefile README.md
git commit -m "feat: 初始化 Monorepo 骨架与工具链"
```

---

### Task 2: BuildingParams 参数模型(核心模块)

**Files:**
- Create: `generation/__init__.py`
- Create: `generation/params/__init__.py`
- Create: `generation/params/model.py`
- Create: `tests/test_params.py`

**Interfaces:**
- Produces: `BuildingParams`(pydantic BaseModel)与 `STYLE_NAMES` 常量。字段与约束见代码。后续 Task 4 的 API schema 与 Task 3 的 DeepSeek 解析都消费此模型。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_params.py
import pytest
from pydantic import ValidationError

from generation.params.model import STYLE_NAMES, BuildingParams


def test_valid_params():
    p = BuildingParams(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass", "stone"],
        roof="flat",
        environment="suburb",
    )
    assert p.floors == 3
    assert p.height_m == pytest.approx(9.6)  # 默认 floors × 3.2


def test_height_override():
    p = BuildingParams(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
        height_m=12.0,
    )
    assert p.height_m == 12.0


def test_style_enum():
    assert STYLE_NAMES == ["modern", "neoclassic", "european", "nordic"]
    with pytest.raises(ValidationError):
        BuildingParams(
            style="baroque",
            floors=3,
            width_m=10.0,
            depth_m=8.0,
            materials=["glass"],
            roof="flat",
            environment="suburb",
        )


def test_bounds():
    with pytest.raises(ValidationError):
        BuildingParams(
            style="modern",
            floors=0,
            width_m=10.0,
            depth_m=8.0,
            materials=["glass"],
            roof="flat",
            environment="suburb",
        )
    with pytest.raises(ValidationError):
        BuildingParams(
            style="modern",
            floors=3,
            width_m=25.0,
            depth_m=8.0,
            materials=["glass"],
            roof="flat",
            environment="suburb",
        )


def test_materials_enum():
    with pytest.raises(ValidationError):
        BuildingParams(
            style="modern",
            floors=3,
            width_m=10.0,
            depth_m=8.0,
            materials=["titanium"],
            roof="flat",
            environment="suburb",
        )


def test_required_fields():
    with pytest.raises(ValidationError):
        BuildingParams(style="modern", floors=3)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_params.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation'`

- [ ] **Step 3: 实现 BuildingParams**

```python
# generation/params/model.py
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Style = Literal["modern", "neoclassic", "european", "nordic"]
Material = Literal["glass", "stone", "brick", "wood"]
Roof = Literal["flat", "pitched", "hipped"]
Environment = Literal["urban", "suburb", "rural", "seaside"]
ViewAngle = Literal["front", "front-3-4"]

STYLE_NAMES = ["modern", "neoclassic", "european", "nordic"]

FLOOR_HEIGHT_M = 3.2  # 默认层高


class BuildingParams(BaseModel):
    """建筑生成参数——所有生成流程的输入契约。"""

    style: Style
    floors: int = Field(ge=1, le=6)
    width_m: float = Field(ge=6, le=20)
    depth_m: float = Field(ge=5, le=18)
    height_m: float | None = Field(default=None, gt=0)
    materials: list[Material] = Field(min_length=1)
    roof: Roof
    environment: Environment
    view_angle: ViewAngle = "front"
    color_scheme: str | None = None

    @model_validator(mode="after")
    def default_height(self) -> "BuildingParams":
        if self.height_m is None:
            self.height_m = self.floors * FLOOR_HEIGHT_M
        return self
```

```python
# generation/params/__init__.py
from generation.params.model import (
    STYLE_NAMES,
    BuildingParams,
    Environment,
    Material,
    Roof,
    Style,
    ViewAngle,
)

__all__ = [
    "STYLE_NAMES",
    "BuildingParams",
    "Environment",
    "Material",
    "Roof",
    "Style",
    "ViewAngle",
]
```

```python
# generation/__init__.py
"""ArchGen 核心生成逻辑包。"""
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_params.py -v`
Expected: 6 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add generation/ tests/test_params.py
git commit -m "feat: 添加 BuildingParams 参数模型与校验"
```

---

### Task 3: DeepSeek 文本客户端

**Files:**
- Create: `generation/llm/__init__.py`
- Create: `generation/llm/deepseek_client.py`
- Create: `tests/test_deepseek_client.py`

**Interfaces:**
- Consumes: `BuildingParams`(Task 2)
- Produces:
  - `DeepSeekClient(api_key: str, base_url: str = "https://api.deepseek.com")`
  - `async def describe_scheme(self, params: BuildingParams, lang: Literal["en", "zh"]) -> str`
  - `async def parse_nl_to_params(self, text: str) -> BuildingParams` — 自然语言→参数(骨架)

- [ ] **Step 1: 写失败的测试(用 mock,不依赖真实 API)**

```python
# tests/test_deepseek_client.py
import pytest
from unittest.mock import AsyncMock, patch

from generation.llm.deepseek_client import DeepSeekClient
from generation.params.model import BuildingParams


@pytest.mark.asyncio
@patch("generation.llm.deepseek_client.AsyncOpenAI")
async def test_describe_scheme_zh(mock_openai):
    mock_chat = AsyncMock()
    mock_chat.completions.create.return_value.choices[0].message.content = "现代风格三层住宅"
    mock_openai.return_value.chat = mock_chat

    client = DeepSeekClient(api_key="test-key")
    params = BuildingParams(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    text = await client.describe_scheme(params, lang="zh")
    assert "现代风格" in text


@pytest.mark.asyncio
@patch("generation.llm.deepseek_client.AsyncOpenAI")
async def test_parse_nl_to_params(mock_openai):
    mock_chat = AsyncMock()
    mock_chat.completions.create.return_value.choices[0].message.content = (
        '{"style": "modern", "floors": 2, "width_m": 9.0, "depth_m": 7.0, '
        '"materials": ["brick"], "roof": "pitched", "environment": "rural"}'
    )
    mock_openai.return_value.chat = mock_chat

    client = DeepSeekClient(api_key="test-key")
    params = await client.parse_nl_to_params("帮我设计一栋两层的乡村砖房")
    assert isinstance(params, BuildingParams)
    assert params.style == "modern"
    assert params.floors == 2
```

- [ ] **Step 2: 添加 pytest-asyncio 依赖**

```bash
uv add --dev pytest-asyncio
```

- [ ] **Step 3: 运行测试验证失败**

Run: `uv run pytest tests/test_deepseek_client.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.llm'`

- [ ] **Step 4: 实现 DeepSeek 客户端**

```python
# generation/llm/deepseek_client.py
import json
import logging
from typing import Literal

from openai import AsyncOpenAI

from generation.params.model import BuildingParams

logger = logging.getLogger(__name__)

DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekClient:
    """DeepSeek 文本层封装——自然语言解析与方案描述。"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def describe_scheme(self, params: BuildingParams, lang: Literal["en", "zh"]) -> str:
        system = (
            "你是一名建筑方案文案助手。根据给定的建筑参数,用简洁专业的中文描述建筑方案。"
            if lang == "zh"
            else "You are an architectural copywriter. Describe the building scheme concisely in English."
        )
        resp = await self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": params.model_dump_json()},
            ],
            temperature=0.7,
        )
        return resp.choices[0].message.content or ""

    async def parse_nl_to_params(self, text: str) -> BuildingParams:
        """自然语言描述 → BuildingParams。要求模型输出严格 JSON。"""
        system = (
            "把用户的自然语言建筑描述转换为 JSON 参数。只输出 JSON,不要额外文字。"
            "字段:style(modern/neoclassic/european/nordic)、floors(1-6)、"
            "width_m(6-20)、depth_m(5-18)、materials(数组,glass/stone/brick/wood)、"
            "roof(flat/pitched/hipped)、environment(urban/suburb/rural/seaside)。"
            "无法确定的字段给合理默认值。"
        )
        resp = await self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("DeepSeek 返回非法 JSON: %s", raw[:200])
            raise ValueError("无法解析建筑参数") from None
        return BuildingParams(**data)
```

```python
# generation/llm/__init__.py
from generation.llm.deepseek_client import DeepSeekClient

__all__ = ["DeepSeekClient"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `uv run pytest tests/test_deepseek_client.py -v`
Expected: 2 个测试全部 PASS

- [ ] **Step 6: 提交**

```bash
git add generation/llm/ tests/test_deepseek_client.py pyproject.toml uv.lock
git commit -m "feat: 添加 DeepSeek 文本客户端(方案描述+NL参数解析)"
```

---

### Task 4: FastAPI 空壳 + /health 与 /api/v1/generate 骨架

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/generate.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/generate.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `BuildingParams`(Task 2)、`DeepSeekClient`(Task 3)
- Produces:
  - `GET /health` → `{"status": "ok"}`
  - `POST /api/v1/generate` 接受 `{params: BuildingParams, lang: "en"|"zh"}`,返回 `{"scheme_id": str, "description": str, "images": []}`(阶段 0 骨架,images 为空占位)
  - `create_app(settings: Settings | None = None) -> FastAPI`
  - `Settings`(pydantic-settings,读取 `.env`)

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_api.py
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _make_app():
    # 显式传参,避免从 .env / 环境变量读取,保证测试确定性
    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
    )
    return create_app(settings)


def test_health():
    client = TestClient(_make_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_generate_skeleton():
    client = TestClient(_make_app())
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
    assert body["images"] == []
    assert "设计" in body["description"]  # 空 key → 占位文案分支


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
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'backend'`

- [ ] **Step 3: 实现 Settings 与 FastAPI 应用**

```python
# backend/app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    image_provider: str = "replicate"  # replicate | fal
    replicate_api_token: str = ""
    cache_dir: str = ".cache/archgen"
    max_free_quota: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# backend/app/main.py
import uvicorn
from fastapi import FastAPI

from backend.app.api.generate import router as generate_router
from backend.app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="ArchGen API", version="0.1.0")
    app.state.settings = settings or get_settings()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(generate_router, prefix="/api/v1")
    return app


def run() -> None:
    """uvicorn 入口(供 `archgen-api` 脚本使用)。"""
    uvicorn.run("backend.app.main:create_app", factory=True, host="0.0.0.0", port=8000)
```

```python
# backend/app/schemas/generate.py
from typing import Literal

from pydantic import BaseModel

from generation.params.model import BuildingParams


class GenerateRequest(BaseModel):
    params: BuildingParams
    lang: Literal["en", "zh"] = "zh"


class GenerationResponse(BaseModel):
    scheme_id: str
    description: str
    images: list[str] = []
```

```python
# backend/app/api/generate.py
import uuid

from fastapi import APIRouter, Request

from backend.app.core.config import Settings
from backend.app.schemas.generate import GenerateRequest, GenerationResponse
from generation.llm.deepseek_client import DeepSeekClient

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: GenerateRequest, request: Request) -> GenerationResponse:
    """生成骨架:校验参数 + 调用 DeepSeek 描述。图片生成在阶段 2 接入。"""
    settings: Settings = request.app.state.settings  # 从 app.state 读取(支持测试注入)
    if not settings.deepseek_api_key:
        description = (
            "测试占位文案:建筑方案描述" if req.lang == "zh" else "Placeholder scheme description"
        )
    else:
        client = DeepSeekClient(settings.deepseek_api_key, settings.deepseek_base_url)
        description = await client.describe_scheme(req.params, req.lang)
    return GenerationResponse(scheme_id=str(uuid.uuid4()), description=description, images=[])
```

- [ ] **Step 4: 补 `__init__.py`**

```bash
touch backend/__init__.py backend/app/__init__.py backend/app/core/__init__.py \
      backend/app/api/__init__.py backend/app/schemas/__init__.py
```

- [ ] **Step 5: 运行测试验证通过**

Run: `uv run pytest tests/ -v`
Expected: 全部测试 PASS(health、generate 骨架、无效参数 422)

- [ ] **Step 7: 运行 lint 并提交**

Run: `uv run ruff check . && uv run ruff format .`
Expected: 无报错,格式化完成。

```bash
git add backend/ tests/
git commit -m "feat: 添加 FastAPI 空壳(/health + /api/v1/generate 骨架)"
```

---

### Task 5: React 前端空壳

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/i18n/en.json`
- Create: `frontend/src/i18n/zh.json`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/components/ParamForm/ParamForm.tsx`

**Interfaces:**
- Produces: `frontend/src/api/client.ts` 导出 `generateScheme(params, lang)`;`ParamForm` 组件(表单骨架,提交后 console.log)

- [ ] **Step 1: 创建前端脚手架文件**

```json
// frontend/package.json
{
  "name": "archgen-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }
}
```

```ts
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
```

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

```html
<!-- frontend/index.html -->
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ArchGen 建筑方案生成</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

```tsx
// frontend/src/App.tsx
import ParamForm from "./components/ParamForm/ParamForm";

export default function App() {
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2rem" }}>
      <h1>ArchGen 建筑方案生成</h1>
      <ParamForm />
    </div>
  );
}
```

```ts
// frontend/src/api/client.ts
export interface BuildingParams {
  style: string;
  floors: number;
  width_m: number;
  depth_m: number;
  materials: string[];
  roof: string;
  environment: string;
  view_angle?: string;
  color_scheme?: string;
}

export interface GenerateResponse {
  scheme_id: string;
  description: string;
  images: string[];
}

export async function generateScheme(params: BuildingParams, lang = "zh"): Promise<GenerateResponse> {
  const resp = await fetch("/api/v1/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ params, lang }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
```

```tsx
// frontend/src/components/ParamForm/ParamForm.tsx
import { useState } from "react";

const STYLES = ["modern", "neoclassic", "european", "nordic"];
const MATERIALS = ["glass", "stone", "brick", "wood"];
const ROOFS = ["flat", "pitched", "hipped"];
const ENVS = ["urban", "suburb", "rural", "seaside"];

export default function ParamForm() {
  const [style, setStyle] = useState("modern");
  const [floors, setFloors] = useState(3);
  const [widthM, setWidthM] = useState(10);
  const [depthM, setDepthM] = useState(8);
  const [material, setMaterial] = useState("glass");

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    console.log({ style, floors, widthM, depthM, material });
  };

  return (
    <form onSubmit={onSubmit} style={{ display: "grid", gap: "1rem" }}>
      <label>风格
        <select value={style} onChange={(e) => setStyle(e.target.value)}>
          {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label>层数
        <input type="number" min={1} max={6} value={floors} onChange={(e) => setFloors(+e.target.value)} />
      </label>
      <label>面宽(m)
        <input type="number" min={6} max={20} value={widthM} onChange={(e) => setWidthM(+e.target.value)} />
      </label>
      <label>进深(m)
        <input type="number" min={5} max={18} value={depthM} onChange={(e) => setDepthM(+e.target.value)} />
      </label>
      <label>材质
        <select value={material} onChange={(e) => setMaterial(e.target.value)}>
          {MATERIALS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </label>
      <button type="submit">生成方案</button>
    </form>
  );
}
```

```json
// frontend/src/i18n/zh.json
{ "app_title": "ArchGen 建筑方案生成", "style": "风格", "floors": "层数" }
```

```json
// frontend/src/i18n/en.json
{ "app_title": "ArchGen Building Generator", "style": "Style", "floors": "Floors" }
```

- [ ] **Step 2: 安装依赖并启动验证**

Run:
```bash
cd frontend && npm install
npm run build
```
Expected: TypeScript 编译通过,无类型错误。

- [ ] **Step 3: 提交**

```bash
git add frontend/
git commit -m "feat: 添加 React 前端空壳(参数表单骨架)"
```

---

### Task 6: CI 工作流(GitHub Actions)

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: 每次 push/PR 自动跑 lint + test

- [ ] **Step 1: 创建 CI 配置**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.11.32"
      - name: Setup Python
        run: uv python install 3.11
      - name: Install deps
        run: uv sync --extra dev
      - name: Lint
        run: uv run ruff check . && uv run ruff format --check .
      - name: Test
        run: uv run pytest -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - name: Install
        run: npm ci
      - name: Build
        run: npm run build
```

- [ ] **Step 2: 在本地模拟 CI 验证**

Run:
```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -v
cd frontend && npm run build
```
Expected: 全部通过,无报错。

- [ ] **Step 3: 提交**

```bash
git add .github/
git commit -m "ci: 添加 GitHub Actions CI(lint + backend tests + frontend build)"
```

---

### Task 7: 端到端冒烟验证(阶段 0 完成标准)

**Files:**
- Modify: 无新文件,运行验证

**Interfaces:**
- Consumes: Task 1-6 的全部产物

- [ ] **Step 1: 启动后端并验证 /health**

Run(终端 A):
```bash
uv run archgen-api
```
Expected: uvicorn 在 8000 端口启动。

Run(终端 B):
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 2: 启动前端并验证页面加载**

Run(终端 C):
```bash
cd frontend && npm run dev
```
Expected: Vite 在 5173 端口启动。

浏览器访问 `http://localhost:5173`,Expected: 页面显示 "ArchGen 建筑方案生成" 与参数表单。

- [ ] **Step 3: 验证 API 代理连通**

浏览器开发者工具 Network,在表单提交后,Expected: 请求 `/api/v1/generate` 经 Vite 代理转发到 `localhost:8000`,返回 200 与 scheme_id。

- [ ] **Step 4: 记录冒烟结果**

Run:
```bash
mkdir -p docs/gallery
echo "# 阶段 0 冒烟验证记录" > docs/gallery/smoke-test.md
echo "- 后端 /health 通过 (2026-08-04)" >> docs/gallery/smoke-test.md
echo "- 前端页面加载通过" >> docs/gallery/smoke-test.md
echo "- /api/v1/generate 返回 scheme_id 与占位描述" >> docs/gallery/smoke-test.md
```

- [ ] **Step 5: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 记录阶段 0 冒烟验证结果"
```

---

## Self-Review

**Spec coverage(对照主计划的阶段 0):**
- ✅ 仓库骨架 → Task 1
- ✅ Makefile + pyproject → Task 1
- ✅ .env.example → Task 1
- ✅ BuildingParams 校验(核心护城河起点)→ Task 2
- ✅ DeepSeek 冒烟(describe + parse)→ Task 3
- ✅ FastAPI 空壳 /health + generate 骨架 → Task 4
- ✅ React 空壳 + 参数表单 → Task 5
- ✅ CI(lint + test + build)→ Task 6
- ✅ 端到端冒烟验证 → Task 7

**Placeholder scan:** 无 TBD/TODO。所有代码块含完整实现。Task 3 的 `parse_nl_to_params` 使用 `response_format={"type": "json_object"}` 提高解析稳定性。

**Type consistency:** `BuildingParams` 字段与测试一致;`Settings` 在 Task 4 被 `create_app(settings)` 注入到 `app.state.settings`,generate 路由通过 `request.app.state.settings` 读取——这保证测试可传入确定性 settings,不依赖 `.env` 或环境变量。`GenerateRequest.params` 复用 `BuildingParams` 类型;前端 `BuildingParams` 接口字段与后端 pydantic 模型字段名一一对应。

**测试确定性说明:** `Settings` 用 `pydantic-settings`,若不显式传参会读环境变量/`.env`。测试中 `_make_app()` 全部显式传参(`deepseek_api_key=""`),确保走"占位文案"分支,不依赖真实 API key。真实 DeepSeek key 分支留待阶段 2 集成测试。
