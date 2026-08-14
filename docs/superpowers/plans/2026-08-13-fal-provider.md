# 多供应商 Fal 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Replicate 之外接入 Fal 作为图片生成供应商(`fal-ai/fast-sdxl-controlnet-canny`),降低供应商锁定风险,为成本/质量对比铺路。

**Architecture:** 新建独立 `FalGenerator`(实现 Generator 协议,镜像 ApiGenerator 的 facade-only 流程:模拟器线稿 → 上传 fal 存储拿 URL → SDXL+ControlNet 真图);Settings 加 `fal_api_key`/`fal_model`,`image_provider` 增 `"fal"` 分支;正式依赖 `fal-client`。prompt.py 与 Generator 协议零改动。

**Tech Stack:** Python 3.11 / FastAPI / pydantic-settings / fal-client(SDK 提供 `upload_file` + `submit_async`) / pytest + ruff(E/F/I/UP/B, line-length=100)。

## Global Constraints

- ruff:`line-length = 100`,`select = ["E", "F", "I", "UP", "B"]`,check + format 双绿
- commit 前缀:`feat:` / `fix:` / `docs:`;消息用中文
- fal 调用一律 mock(本机无真调,参照 `tests/test_replicate_gen.py` 的 MagicMock 模式)
- 不改:SimulatorGenerator、ApiGenerator/replicate_gen.py、prompt.py、Generator 协议、前端、quota
- facade-only:floorplan 保持模拟器线稿(SDXL 不适合平面图已真调证实)
- 本期不做 LoRA 注入(fal 的 loras 参数格式与 replicate 不同,对齐时再做)
- `fal_gen.py` **不在模块顶层 import fal_client**(客户端经 `__init__` 参数注入,与 ApiGenerator 注入 replicate_client 同模式);路由分支内 lazy `import fal_client`
- 无 `fal_api_key` 且 provider=fal → HTTP 500「fal_api_key 未配置」(与 replicate 分支同风格)
- 真调留待人工(需 FAL_KEY token),代码落地 + mock 绿即视为本期完成
- 设计文档 `docs/superpowers/specs/2026-08-13-fal-provider-design.md` 为唯一需求来源,若实现需偏离须先经用户批准

---

### Task 1: FalGenerator 独立类 + 单元测试

**Files:**
- Create: `generation/generators/api/fal_gen.py`
- Test: `tests/test_fal_gen.py`

**Interfaces:**
- Consumes:
  - `build_prompt(params, kind, lang)` / `build_negative_prompt()`(generation.generators.api.prompt,现有)
  - `render_scheme(params, scheme_id, out_dir, lang)`(generation.generators.simulator.renderer,现有)
  - `GenerationArtifact` / `ImageRef`(generation.generators.base,现有)
- Produces:
  - `class FalGenerator` 位于 `generation.generators.api.fal_gen`
  - `FalGenerator.__init__(self, fal_client=None, model: str = FAL_MODEL)` — fal_client 为 None 抛 `FalGeneratorError`
  - `FalGenerator.generate(params, scheme_id, out_dir, lang) -> GenerationArtifact`(Generator 协议)
  - `FAL_MODEL = "fal-ai/fast-sdxl-controlnet-canny"` 常量(Task 2 路由 import)

- [ ] **Step 1: 写失败测试**

创建 `tests/test_fal_gen.py`:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_fal_gen.py -v`
Expected: 3 个 FAIL(ModuleNotFoundError:`generation.generators.api.fal_gen` 不存在)

- [ ] **Step 3: 实现**

创建 `generation/generators/api/fal_gen.py`:

```python
import asyncio
import urllib.request
from pathlib import Path

from generation.generators.api.prompt import build_negative_prompt, build_prompt
from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams

# fal ControlNet SDXL(canny 版,与 replicate 的 controlnet-sdxl 对等)。
FAL_MODEL = "fal-ai/fast-sdxl-controlnet-canny"
CONTROLNET_CONDITIONING_SCALE = 0.5  # 与 replicate 的 condition_scale 0.5 对齐
FAL_STEPS = 30
FAL_GUIDANCE = 7.5
FAL_WAIT_SECONDS = 300

FACADE_FILE = "facade.png"
FLOORPLAN_FILE = "floorplan.png"


class FalGeneratorError(Exception):
    """Fal generator configuration / invocation error."""


class FalGenerator:
    """Fal SDXL + ControlNet generator — implements the Generator protocol.

    Flow: simulator line-art as ControlNet condition image (uploaded to fal
    storage for a public URL) -> SDXL real facade; floorplan stays simulator
    line-art.
    """

    def __init__(self, fal_client=None, model: str = FAL_MODEL):
        if fal_client is None:
            raise FalGeneratorError("fal client not provided (set fal_api_key)")
        self._client = fal_client
        self._model = model

    async def _upload_lineart(self, path: Path) -> str:
        """Upload the condition image to fal storage, return its public URL."""
        return await asyncio.to_thread(self._client.upload_file, path)

    async def _call_fal(self, prompt: str, control_url: str, out_path: Path) -> None:
        sdxl_input = {
            "prompt": prompt,
            "negative_prompt": build_negative_prompt(),
            "control_image_url": control_url,
            "controlnet_conditioning_scale": CONTROLNET_CONDITIONING_SCALE,
            "num_inference_steps": FAL_STEPS,
            "guidance_scale": FAL_GUIDANCE,
            "image_size": {"width": 1024, "height": 1024},
            "num_images": 1,
            "seed": 42,
        }
        handle = await self._client.submit_async(
            self._model, arguments=sdxl_input, timeout=FAL_WAIT_SECONDS
        )
        result = await handle.get()  # get() 阻塞轮询直到完成
        url = result["images"][0]["url"]
        urllib.request.urlretrieve(url, str(out_path))

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: Path,
        lang: str = "zh",
    ) -> GenerationArtifact:
        # 与 ApiGenerator 同骨架:线稿条件图 → 真模型 facade,floorplan 留模拟器线稿
        await render_scheme(params, scheme_id, out_dir, lang)
        line_facade = out_dir / FACADE_FILE
        facade_line = out_dir / "facade_line.png"
        if line_facade.exists():
            line_facade.rename(facade_line)
        prompt = build_prompt(params, "facade", lang)
        control_url = await self._upload_lineart(facade_line)
        await self._call_fal(prompt, control_url, out_dir / FACADE_FILE)
        facade_line.unlink(missing_ok=True)
        return GenerationArtifact(
            scheme_id=scheme_id,
            images=[
                ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
                ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
            ],
        )


__all__ = ["FalGenerator", "FalGeneratorError"]
```

计划修正说明:spec 草案写的是 `start_timeout` 参数,但 fal SDK 的 `start_timeout` 只限制「排队开始」期限;请求总超时(排队+处理)是 `timeout` 参数——实现用 `timeout=FAL_WAIT_SECONDS`,与 replicate 的 wait=300(总时长)语义对称。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_fal_gen.py -v`
Expected: 3 个 PASS

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check generation/generators/api/fal_gen.py tests/test_fal_gen.py && uv run ruff format --check generation/generators/api/fal_gen.py tests/test_fal_gen.py`
Expected: 无告警

```bash
git add generation/generators/api/fal_gen.py tests/test_fal_gen.py
git commit -m "feat: 新增 FalGenerator(上传线稿作条件图 + submit_async 真图,facade-only)"
```

---

### Task 2: Settings + 路由 fal 分支 + fal-client 依赖

**Files:**
- Modify: `backend/app/core/config.py:16`(Settings 加字段)
- Modify: `backend/app/api/generate.py:43-57`(image_provider 增 fal 分支)
- Modify: `pyproject.toml:12`(dependencies 加 fal-client)
- Test: `tests/test_api.py`(路由测试)+ `tests/test_replicate_gen.py`(Settings 字段测试)

**Interfaces:**
- Consumes:
  - `FalGenerator` / `FAL_MODEL`(Task 1,`generation.generators.api.fal_gen`)
- Produces:
  - `Settings.fal_api_key: str = ""` — 空=不可用
  - `Settings.fal_model: str = ""` — 空=用默认 FAL_MODEL
  - `image_provider="fal"` 路由分支:无 token → 500;有 token → `FalGenerator(fal_client=<module>, model=settings.fal_model or FAL_MODEL)`

- [ ] **Step 1: 写失败测试(追加到 tests/test_api.py 末尾)**

```python
def test_generate_uses_falgenerator_when_fal(tmp_path):
    from unittest.mock import AsyncMock, patch

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
```

追加到 `tests/test_replicate_gen.py`(Settings 字段测试):

```python
def test_settings_fal_fields_default_empty():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=".tmp-test",
    )
    assert settings.fal_api_key == ""
    assert settings.fal_model == ""


def test_settings_fal_fields_can_be_set():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="fal",
        max_free_quota=5,
        cache_dir=".tmp-test",
        fal_api_key="fal-key-123",
        fal_model="fal-ai/fast-sdxl-controlnet-canny",
    )
    assert settings.fal_api_key == "fal-key-123"
    assert settings.fal_model == "fal-ai/fast-sdxl-controlnet-canny"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_api.py::test_generate_uses_falgenerator_when_fal tests/test_api.py::test_generate_fal_missing_token_returns_500 tests/test_replicate_gen.py::test_settings_fal_fields_default_empty tests/test_replicate_gen.py::test_settings_fal_fields_can_be_set -v`
Expected: 4 个 FAIL(`fal_api_key`/`fal_model` 字段不存在;image_provider="fal" 走 else 分支 SimulatorGenerator)

- [ ] **Step 3: 实现**

**修改 `backend/app/core/config.py`** — `quota_storage_path` 之后加:

```python
    fal_api_key: str = ""  # fal 密钥,空=不可用
    fal_model: str = ""  # fal 模型名,空=用默认 FAL_MODEL
```

**修改 `backend/app/api/generate.py`** — import 区在 `from generation.generators.api import ApiGenerator` 之后加:

```python
from generation.generators.api.fal_gen import FAL_MODEL, FalGenerator
```

replicate 分支的 `else:` 改为 `elif settings.image_provider == "fal":` 分支 + 保留 else simulator:

```python
    elif settings.image_provider == "fal":
        if not settings.fal_api_key:
            raise HTTPException(status_code=500, detail="fal_api_key 未配置")
        import fal_client

        generator = FalGenerator(
            fal_client=fal_client,
            model=settings.fal_model or FAL_MODEL,
        )
    else:
        generator = SimulatorGenerator()
```

**修改 `pyproject.toml`** — `dependencies` 中 `"replicate>=1.0",` 之后加:

```toml
    "fal-client>=0.7",
```

然后同步依赖:

Run: `uv sync`
Expected: fal-client 安装成功,uv.lock 更新(uv.lock 一起提交)

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_api.py tests/test_replicate_gen.py -v`
Expected: 新增 4 个 PASS,原有测试仍 PASS

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check backend/app/core/config.py backend/app/api/generate.py tests/test_api.py tests/test_replicate_gen.py && uv run ruff format --check backend/app/core/config.py backend/app/api/generate.py tests/test_api.py tests/test_replicate_gen.py`
Expected: 双绿

```bash
git add backend/app/core/config.py backend/app/api/generate.py pyproject.toml uv.lock tests/test_api.py tests/test_replicate_gen.py
git commit -m "feat: Settings 新增 fal_api_key/fal_model,image_provider 增 fal 分支(依赖 fal-client)"
```

---

### Task 3: 全量回归 + smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`

**Interfaces:**
- Consumes: Task 1-2 全部改动
- Produces: 冒烟验证记录(fal 落地证据)

- [ ] **Step 1: 全量测试 + ruff 双绿**

Run: `uv run pytest -q`
Expected: 111(原有)+ 3(Task1)+ 4(Task2)= **118 passed + 1 skipped**(`test_training_skip.py` 本机无 torch 跳过)
Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 双绿

- [ ] **Step 2: 追加 smoke-test 记录**

在 `docs/gallery/smoke-test.md` 末尾追加:

```markdown
# 多供应商 Fal 验证记录 (2026-08-13)

- FalGenerator 独立类:镜像 ApiGenerator 的 facade-only 流程;线稿 upload_file 上传拿 URL 作 control_image_url;submit_async(timeout=300)+ handle.get() 拿 images[0].url 落盘
- 输入对齐 replicate:controlnet_conditioning_scale 0.5、steps 30、guidance 7.5、seed 42、1024×1024
- Settings 新增 fal_api_key/fal_model(默认空);image_provider 增 "fal" 分支,无 token 500;正式依赖 fal-client
- prompt.py 与 Generator 协议零改动;prompt 构造复用 build_prompt
- mock 单测:artifact 流程/上传+参数断言/缺客户端报错 3 例 + 路由 2 例 + Settings 2 例
- 全量回归:118 passed + 1 skipped;ruff check + format 双绿
- 真调留待人工:需 FAL_KEY token(.env 配 FAL_API_KEY + IMAGE_PROVIDER=fal);真调时对比两供应商成本/质量
- 遗留:LoRA 注入(fal 的 loras 参数格式与 replicate 不同,对齐时再做);供应商自动故障切换
```

- [ ] **Step 3: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 多供应商 Fal 验证记录(全量回归 + 真调留待人工)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| `FalGenerator` 实现 Generator 协议(facade-only) | Task 1 | `test_generate_returns_artifact` |
| 线稿 upload_file 上传拿 URL | Task 1 | `test_uploads_lineart_and_passes_arguments`(upload_file assert_called_once) |
| 输入:scale 0.5 / steps 30 / guidance 7.5 / seed 42 / 1024×1024 | Task 1 | 参数断言 |
| 输出 images[0].url 落盘 facade.png | Task 1 | urlretrieve 断言 facade.png 内容 |
| 条件图清理 | Task 1 | `assert not facade_line.png.exists()` |
| 缺 fal_client 抛 FalGeneratorError | Task 1 | `test_missing_client_raises` |
| `Settings.fal_api_key` / `fal_model` 默认空 | Task 2 | Settings 2 例 |
| `image_provider="fal"` + token → FalGenerator;无 token → 500 | Task 2 | 路由 2 例 |
| fal-client 正式依赖 + uv.lock | Task 2 | pyproject + uv sync |
| prompt.py / Generator 协议 / replicate_gen.py 零改动 | 全计划 | diff 检查 |
| 全量回归 118 passed + 1 skipped | Task 3 | `uv run pytest -q` |
| 真调留待人工(需 FAL_KEY) | Task 3 | smoke-test 记录 |
