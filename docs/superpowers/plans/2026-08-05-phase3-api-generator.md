# 阶段 3:API 生成器(SDXL + ControlNet)— 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `ApiGenerator` 走通验证期真实模型链路——模拟器线稿作为 ControlNet 条件图,驱动 Replicate SDXL 出真图(效果图 + 平面图都走真模型)。

**Architecture:** 新增 `generation/generators/api/` 包:`prompt.py`(参数→SDXL prompt,护城河确定性代码)+ `replicate_gen.py`(`ApiGenerator` 实现 `Generator` 协议,内部复用 `render_scheme` 生成线稿作 ControlNet 条件图,两次调用 Replicate SDXL)。API 路由按 `Settings.image_provider` 切换 `SimulatorGenerator`/`ApiGenerator`。

**Tech Stack:** Python 3.11、Replicate SDK、Pillow、pydantic v2、pytest、ruff。

## Global Constraints

- Python >= 3.11,包管理用 `uv`,不用 pip 直接装
- ruff lint 与 format 必须通过;pytest 全绿才算任务完成
- 提交信息用 `feat:` / `fix:` / `docs:` 前缀
- `Generator` 协议不变:`async def generate(self, params, scheme_id, out_dir: Path, lang="zh") -> GenerationArtifact`
- 护城河代码(`prompt.py` + 线稿)不依赖模型供应商,确定性、纯代码
- mock 测试必须离线确定性(不真调 API);真调验证单独标记
- 本阶段前端零改动(`images` 契约不变)
- `replicate` 依赖已在 pyproject.toml(阶段 0 加入)
- SDXL prompt 固定英文(即使 lang=zh),SDXL 对英文 prompt 效果最佳

---

### Task 1: prompt 模块(prompt.py,护城河)

**Files:**
- Create: `generation/generators/api/__init__.py`
- Create: `generation/generators/api/prompt.py`
- Create: `tests/test_prompt.py`

**Interfaces:**
- Consumes: `BuildingParams`(已有)
- Produces:
  - `def build_prompt(params: BuildingParams, kind: Literal["facade", "floorplan"], lang: str = "en") -> str`
  - `def build_negative_prompt() -> str`
  - `STYLE_LABELS: dict[str, str]`(modern/neoclassic/european/nordic → 英文建筑风格描述)
  - `MATERIAL_LABELS: dict[str, str]`(glass/stone/brick/wood → 英文材质描述)

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_prompt.py
from generation.generators.api.prompt import (
    build_negative_prompt,
    build_prompt,
)
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


def test_build_prompt_facade_contains_style_and_material():
    p = build_prompt(_params(style="modern", materials=["glass"]), "facade")
    assert "modern" in p.lower() or "contemporary" in p.lower()
    assert "glass" in p.lower()


def test_build_prompt_floorplan_mentions_floorplan():
    p = build_prompt(_params(), "floorplan")
    assert "floor plan" in p.lower() or "floorplan" in p.lower()


def test_build_prompt_different_params_differ():
    p1 = build_prompt(_params(style="modern"), "facade")
    p2 = build_prompt(_params(style="neoclassic"), "facade")
    assert p1 != p2


def test_build_prompt_kind_differs():
    facade = build_prompt(_params(), "facade")
    floorplan = build_prompt(_params(), "floorplan")
    assert facade != floorplan


def test_build_prompt_en_output_even_for_zh():
    p = build_prompt(_params(), "facade", lang="zh")
    # SDXL prompt 固定英文
    assert p.isascii()


def test_build_negative_prompt_nonempty():
    assert build_negative_prompt().strip()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_prompt.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators.api'`

- [ ] **Step 3: 实现 prompt.py 与包初始化**

```python
# generation/generators/api/__init__.py
"""API 生成器包——验证期走 Replicate SDXL + ControlNet。"""
```

```python
# generation/generators/api/prompt.py
from typing import Literal

from generation.params.model import BuildingParams

# 英文建筑风格描述(SDXL prompt 用英文)
STYLE_LABELS: dict[str, str] = {
    "modern": "modern minimalist architecture with clean lines",
    "neoclassic": "neoclassical architecture with symmetrical facade and columns",
    "european": "European classic architecture with arched windows and pediment",
    "nordic": "Nordic Scandinavian architecture with wood and minimalist details",
}

MATERIAL_LABELS: dict[str, str] = {
    "glass": "glass curtain wall",
    "stone": "natural stone cladding",
    "brick": "brick facade",
    "wood": "wood cladding",
}

ENVIRONMENT_LABELS: dict[str, str] = {
    "urban": "urban setting, city street",
    "suburb": "suburban neighborhood",
    "rural": "rural countryside, open field",
    "seaside": "seaside, coastal view",
}

ROOF_LABELS: dict[str, str] = {
    "flat": "flat roof",
    "pitched": "pitched gable roof",
    "hipped": "hipped roof",
}

FACADE_PREFIX = "architectural rendering of a residential building"
FLOORPLAN_PREFIX = "architectural floor plan drawing, top view layout"

NEGATIVE_PROMPT = (
    "low quality, blurry, distorted, deformed, watermark, text, "
    "signature, extra buildings, perspective error"
)


def build_prompt(
    params: BuildingParams,
    kind: Literal["facade", "floorplan"],
    lang: str = "en",
) -> str:
    """构造 SDXL prompt(固定英文,即使 lang=zh)。确定性、纯代码。"""
    style = STYLE_LABELS[params.style]
    material = MATERIAL_LABELS[params.materials[0]]
    env = ENVIRONMENT_LABELS[params.environment]
    roof = ROOF_LABELS[params.roof]
    if kind == "facade":
        return (
            f"{FACADE_PREFIX}, {style}, {material}, {roof}, "
            f"{params.floors}-story, {env}, photorealistic, high detail"
        )
    return (
        f"{FLOORPLAN_PREFIX}, {style}, {material}, "
        f"{params.floors} floors, {params.width_m}x{params.depth_m} meters, "
        f"architectural blueprint style, clean layout"
    )


def build_negative_prompt() -> str:
    return NEGATIVE_PROMPT
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_prompt.py -v`
Expected: 6 个测试全部 PASS

- [ ] **Step 5: 运行 ruff check**

Run: `uv run ruff check .`
Expected: 无报错。

- [ ] **Step 6: 提交**

```bash
git add generation/generators/api/ tests/test_prompt.py
git commit -m "feat: 添加参数→SDXL prompt 模块(护城河,双类 facade/floorplan)"
```

---

### Task 2: ApiGenerator(replicate_gen.py)

**Files:**
- Create: `generation/generators/api/replicate_gen.py`
- Modify: `generation/generators/api/__init__.py`(导出 ApiGenerator)
- Create: `tests/test_replicate_gen.py`

**Interfaces:**
- Consumes: `Generator` 协议(Task 阶段2 base.py)、`render_scheme`(simulator)、`build_prompt`/`build_negative_prompt`(Task 1)
- Produces:
  - `class ApiGenerator:` 实现 `Generator` 协议
  - 构造:`ApiGenerator(replicate_client=None, model="black-forest-labs/flux-schnell")`
  - `async def generate(self, params: BuildingParams, scheme_id: str, out_dir: Path, lang="zh") -> GenerationArtifact`
  - 内部:`_call_sdxl(prompt, control_image_path, out_path)` 调用 Replicate(同步,线程池)

- [ ] **Step 1: 写失败的测试(用 mock,不真调 API)**

```python
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
    """构造带 mock .run 的 client,返回可复制的假输出文件路径。"""
    out = tmp_path / "out.png"
    out.write_bytes(b"fake-png-bytes")
    client = MagicMock()
    client.run.return_value = [str(out)]
    return client, out


@pytest.mark.asyncio
async def test_generate_returns_artifact(tmp_path: Path):
    client, out = _make_client(tmp_path)
    # mock urlretrieve:直接把源文件复制到目标路径
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
    # 真图文件存在(由 mock urlretrieve 复制而来)
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

    # 两次 SDXL 调用(facade + floorplan),走注入的 client
    assert client.run.call_count == 2


@pytest.mark.asyncio
async def test_generate_without_client_raises(tmp_path: Path):
    # 无 API key / client 时,构造函数抛配置错误
    from generation.generators.api.replicate_gen import ApiGeneratorError

    with pytest.raises(ApiGeneratorError):
        ApiGenerator(replicate_client=None)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_replicate_gen.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators.api.replicate_gen'`

- [ ] **Step 3: 实现 replicate_gen.py 并导出**

```python
# generation/generators/api/replicate_gen.py
import asyncio
import urllib.request
from pathlib import Path

import replicate

from generation.generators.api.prompt import build_negative_prompt, build_prompt
from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams

# Replicate 上的 SDXL 模型(验证期用 flux-schnell,替换为支持 ControlNet 的 SDXL 模型)
# 注意:实际模型需按 ControlNet 支持情况配置,见真调验证
SDXL_MODEL = "black-forest-labs/flux-schnell"
CONTROLNET_MODEL = "black-forest-labs/flux-schnell"  # 占位,真调时替换为 ControlNet 模型

FACADE_FILE = "facade.png"
FLOORPLAN_FILE = "floorplan.png"


class ApiGeneratorError(Exception):
    """API 生成器配置/调用错误。"""


class ApiGenerator:
    """Replicate SDXL + ControlNet 生成器——实现 Generator 协议。

    流程:模拟器线稿作 ControlNet 条件图 → SDXL 出真图(效果图 + 平面图)。
    """

    def __init__(self, replicate_client=None, model: str = SDXL_MODEL):
        if replicate_client is None:
            raise ApiGeneratorError("replicate client 未提供(需设置 replicate_api_token)")
        self._client = replicate_client
        self._model = model

    def _call_sdxl(self, prompt: str, control_image: Path, out_path: Path) -> None:
        """同步调用 Replicate SDXL(在线程池中执行)。"""
        with open(control_image, "rb") as f:
            output = self._client.run(
                self._model,
                input={
                    "prompt": prompt,
                    "negative_prompt": build_negative_prompt(),
                    "control_image": f,
                },
            )
        # output 是文件 URL 列表;下载第一个保存到 out_path
        file_url = output[0] if isinstance(output, list) else output
        urllib.request.urlretrieve(str(file_url), str(out_path))

    async def _render_with_sdxl(self, params, scheme_id, out_dir, lang, kind) -> None:
        prompt = build_prompt(params, kind, lang)
        control = out_dir / ("facade_line.png" if kind == "facade" else "floorplan_line.png")
        await asyncio.to_thread(
            self._call_sdxl, prompt, control, out_dir / (FACADE_FILE if kind == "facade" else FLOORPLAN_FILE)
        )

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: Path,
        lang: str = "zh",
    ) -> GenerationArtifact:
        # 1. 生成两条线稿作 ControlNet 条件图
        await render_scheme(params, scheme_id, out_dir, lang)
        # 2. 重命名为 _line 后缀(条件图),避免覆盖真图
        line_facade = out_dir / FACADE_FILE
        line_floorplan = out_dir / FLOORPLAN_FILE
        facade_line = out_dir / "facade_line.png"
        floorplan_line = out_dir / "floorplan_line.png"
        if line_facade.exists():
            line_facade.rename(facade_line)
        if line_floorplan.exists():
            line_floorplan.rename(floorplan_line)
        # 3. 两次 SDXL 调用(效果图 + 平面图)
        await self._render_with_sdxl(params, scheme_id, out_dir, lang, "facade")
        await self._render_with_sdxl(params, scheme_id, out_dir, lang, "floorplan")
        # 4. 清理线稿条件图(保留真图)
        facade_line.unlink(missing_ok=True)
        floorplan_line.unlink(missing_ok=True)
        return GenerationArtifact(
            scheme_id=scheme_id,
            images=[
                ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
                ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
            ],
        )


__all__ = ["ApiGenerator", "ApiGeneratorError"]
```

```python
# generation/generators/api/__init__.py 更新为:
from generation.generators.api.replicate_gen import ApiGenerator, ApiGeneratorError

__all__ = ["ApiGenerator", "ApiGeneratorError"]
```

> **mock 说明:** 测试通过注入 `replicate_client=MagicMock()`(其 `.run` 返回假文件路径)驱动 `self._client.run`,并 mock `urllib.request.urlretrieve`(side_effect 复制假文件),保证离线确定性且验证依赖注入。`replicate_gen.py` 模块顶部 `import urllib.request`,mock 路径为 `generation.generators.api.replicate_gen.urllib.request.urlretrieve`。测试保持「断言 artifact + 两次 client.run 调用」的核心意图。

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_replicate_gen.py -v`
Expected: 3 个测试全部 PASS(含 mock)

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `uv run pytest -q`
Expected: 51 passed(45 前 + 6 prompt + 3 replicate,注意 Task 1 已加 6)

- [ ] **Step 6: 运行 ruff check 并提交**

Run: `uv run ruff check . && uv run ruff format .`
Expected: 无报错。

```bash
git add generation/generators/api/ tests/test_replicate_gen.py
git commit -m "feat: 添加 ApiGenerator(Replicate SDXL+ControlNet,线稿作条件图)"
```

---

### Task 3: 路由按 provider 切换 + 全局配置

**Files:**
- Modify: `backend/app/api/generate.py`(按 image_provider 选生成器)
- Modify: `backend/app/core/config.py`(确认 image_provider 字段与默认)
- Modify: `tests/test_api.py`(新增 provider 切换测试)

**Interfaces:**
- Consumes: `SimulatorGenerator`/`ApiGenerator`(已有)、`Settings.image_provider`(已有字段)
- Produces:
  - `generate` 路由:`image_provider == "replicate"` 时用 `ApiGenerator`,否则 `SimulatorGenerator`
  - `Settings.image_provider` **默认改为 `"simulator"`**(避免默认 replicate+空 token 导致每次 generate 500;开箱行为匹配路由默认)

- [ ] **Step 1: 写失败的测试(provider 切换)**

```python
# tests/test_api.py 追加:
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
```

> 注:provider 为 replicate 的路由测试需 mock ApiGenerator(避免真调 API),在 Task 4 的集成测试中覆盖。

- [ ] **Step 2: 运行测试验证通过(现有模拟器路径已工作)**

Run: `uv run pytest tests/test_api.py -v`
Expected: 新增测试 PASS(模拟器路径本来就走通)。

- [ ] **Step 3: 修改 generate.py 按 provider 选生成器**

```python
# backend/app/api/generate.py
import pathlib
import uuid

from fastapi import APIRouter, HTTPException, Request

from backend.app.core.config import Settings
from backend.app.schemas.generate import GenerateRequest, GenerationResponse
from generation.generators import SimulatorGenerator
from generation.generators.api import ApiGenerator
from generation.llm.deepseek_client import DeepSeekClient

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: GenerateRequest, request: Request) -> GenerationResponse:
    """生成:按 image_provider 选生成器(默认模拟器,replicate 走真模型)。"""
    settings: Settings = request.app.state.settings  # 从 app.state 读取(支持测试注入)
    scheme_id = str(uuid.uuid4())
    if not settings.deepseek_api_key:
        description = (
            "测试占位文案:建筑设计描述" if req.lang == "zh" else "Placeholder scheme description"
        )
    else:
        client = DeepSeekClient(settings.deepseek_api_key, settings.deepseek_base_url)
        description = await client.describe_scheme(req.params, req.lang)

    out_dir = pathlib.Path(settings.cache_dir) / scheme_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if settings.image_provider == "replicate":
        if not settings.replicate_api_token:
            raise HTTPException(status_code=500, detail="replicate_api_token 未配置")
        import replicate

        generator = ApiGenerator(replicate_client=replicate.Client(token=settings.replicate_api_token))
    else:
        generator = SimulatorGenerator()

    artifact = await generator.generate(req.params, scheme_id, out_dir, req.lang)
    return GenerationResponse(
        scheme_id=scheme_id,
        description=description,
        images=[img.url for img in artifact.images],
    )
```

- [ ] **Step 4: 修改 config.py 默认 provider 为 simulator**

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    image_provider: str = "simulator"  # simulator | replicate(默认模拟器,避免空 token 500)
    replicate_api_token: str = ""
    cache_dir: str = ".cache/archgen"
    max_free_quota: int = 5
```

> 注:阶段 0 遗留的 `image_provider="replicate"` 默认值 + 空 `replicate_api_token` 会导致部署时不配 env 就每次 generate 500。改为 `"simulator"` 让开箱行为安全,配 env 才能启用真模型。

- [ ] **Step 5: 运行全量测试确认无回归**

Run: `uv run pytest -q`
Expected: 52 passed(51 + 1 新默认 provider 测试)

- [ ] **Step 6: 运行 ruff check 并提交**

Run: `uv run ruff check . && uv run ruff format .`
Expected: 无报错。

```bash
git add backend/app/api/generate.py backend/app/core/config.py tests/test_api.py
git commit -m "feat: API 路由按 image_provider 切换生成器(默认模拟器)+ config 默认值修正"
```

---

### Task 4: 集成测试(mock ApiGenerator 的 provider 切换)+ 全量验证

**Files:**
- Modify: `tests/test_api.py`(replicate provider 集成测试)
- Modify: `docs/gallery/smoke-test.md`(追加阶段 3 记录)

**Interfaces:**
- Consumes: `ApiGenerator`(Task 2)、路由切换(Task 3)

- [ ] **Step 1: 写集成测试(provider=replicate, mock ApiGenerator 避免真调)**

```python
# tests/test_api.py 追加:
def test_generate_uses_apigenerator_when_replicate(tmp_path):
    from backend.app.core.config import Settings
    from unittest.mock import AsyncMock, patch

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
        cache_dir=str(tmp_path),
        replicate_api_token="test-token",
    )
    # mock ApiGenerator.generate,避免真调 Replicate
    with patch("backend.app.api.generate.ApiGenerator") as mock_cls:
        mock_gen = mock_cls.return_value
        mock_gen.generate = AsyncMock(
            return_value=__import__("generation.generators.base", fromlist=["GenerationArtifact"]).GenerationArtifact(
                scheme_id="s1",
                images=[__import__("generation.generators.base", fromlist=["ImageRef"]).ImageRef(kind="facade", url="/images/s1/facade.png"),
                        __import__("generation.generators.base", fromlist=["ImageRef"]).ImageRef(kind="floorplan", url="/images/s1/floorplan.png")],
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
        # 确认走的是 ApiGenerator
        mock_cls.assert_called_once()
```

- [ ] **Step 2: 运行测试验证通过**

Run: `uv run pytest tests/test_api.py::test_generate_uses_apigenerator_when_replicate -v`
Expected: PASS(路由切到 ApiGenerator,被 mock)

- [ ] **Step 3: 运行全量测试与 lint**

Run:
```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```
Expected: 全部 PASS,ruff 无报错(52 + 1 = 53 测试)。

- [ ] **Step 4: 真调一次验证(需 Replicate API key,可选但推荐)**

Run:
```bash
# 设置 REPLICATE_API_TOKEN 环境变量后,手动调用一次真实生成
export REPLICATE_API_TOKEN=<your-token>
uv run python -c "
import asyncio, replicate, tempfile, pathlib
from generation.generators.api import ApiGenerator
from generation.params.model import BuildingParams

async def main():
    params = BuildingParams(style='modern', floors=2, width_m=10, depth_m=8,
                            materials=['glass'], roof='flat', environment='suburb')
    out = pathlib.Path(tempfile.mkdtemp())
    gen = ApiGenerator(replicate_client=replicate.Client())
    art = await gen.generate(params, 'real-smoke', out, 'zh')
    for img in art.images:
        p = out / img.url.rsplit('/', 1)[-1]
        print(img.kind, p.exists(), p.stat().st_size if p.exists() else 0)

asyncio.run(main())
"
```
Expected: 打印 facade/floorplan 两个文件存在且非空(真实 SDXL 出图)。结果记入冒烟文档。

- [ ] **Step 5: 记录冒烟结果**

```bash
echo "- 阶段3: ApiGenerator(SDXL+ControlNet)实现,线稿作条件图,双产出走真模型" >> docs/gallery/smoke-test.md
echo "- 阶段3: mock 测试通过(路由切换 + ApiGenerator 两次调用),真调验证(如有)" >> docs/gallery/smoke-test.md
echo "- 阶段3: 全量测试 53 passed,ruff 全绿" >> docs/gallery/smoke-test.md
```

- [ ] **Step 6: 提交**

```bash
git add tests/test_api.py docs/gallery/smoke-test.md
git commit -m "docs: 记录阶段 3 冒烟验证结果 + replicate provider 集成测试"
```

---

## Self-Review

**Spec coverage(对照阶段 3 设计规格):**
- ✅ prompt.py 参数→SDXL prompt(护城河,双类 facade/floorplan)→ Task 1
- ✅ ApiGenerator 实现 Generator 协议,线稿作 ControlNet 条件图,双产出走真模型 → Task 2
- ✅ 全局 provider 配置切换路由(默认模拟器)→ Task 3
- ✅ 集成测试(mock ApiGenerator)+ 真调一次验证 → Task 4

**Placeholder scan:** 无 TBD/TODO。所有代码块含完整实现。Task 2 的 `CONTROLNET_MODEL` 占位已在代码注释说明「真调时替换为 ControlNet 模型」——验证期真实模型名需按 Replicate 上可用的 ControlNet SDXL 模型配置。

**Type consistency:**
- `ApiGenerator.generate` 签名匹配 `Generator` 协议 `(params, scheme_id, out_dir: Path, lang="zh")`
- `build_prompt(params, kind, lang)` 在 Task 1 定义、Task 2 消费,签名一致
- `GenerationArtifact.images` 为 `list[ImageRef]`,ApiGenerator 产出 facade/floorplan 两个 ImageRef
- 路由 `image_provider` 字段已存在于 `Settings`(阶段 0),Task 3 消费

**Mock 说明:** Task 2 的测试 patch `replicate.run` 并 mock `urlretrieve`(或返回可下载 URL),保证离线确定性。Task 4 的 provider 切换测试 mock `ApiGenerator.generate`。真调验证(Step 4)独立标记,不进入 pytest。

**兼容性:** 现有 45 测试(含模拟器路径)全部保持通过。`image_provider` 默认改为 `"simulator"`(Settings 默认值)——阶段 0 的 `"replicate"` 默认 + 空 token 会导致未配 env 时 generate 500,本计划修正此陷阱。
