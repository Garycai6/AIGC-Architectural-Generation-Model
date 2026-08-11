# 里程碑3.5:LoRA 接入网页生成 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 网页 replicate 模式的效果图按风格注入对应 SDXL LoRA(公网 URL 引用),缓解 SDXL 固有幻觉;未配置时行为完全向后兼容。

**Architecture:** 设计文档「路径 A:自托管权重 URL + 推理注入」。`Settings` 新增 `sdxl_model`(模型名,空=默认)与 `lora_weights_dir`(风格 LoRA 公网 URL 目录,空=不注入);`ApiGenerator` 构造时接收 `lora_urls: dict[str,str]`(风格→URL),`_render_facade_sdxl` 按 `params.style` 查表,查到则 `_call_sdxl` 注入 `"lora_weights"` 字段,查不到降级不注入;`generate.py` 的 replicate 分支按 `{dir}/{style}.tar` 约定组装 `lora_urls`。

**Tech Stack:** Python 3.11 / FastAPI / pydantic-settings / replicate SDK / pytest(MagicMock)+ ruff(E/F/I/UP/B)。

## Global Constraints

- ruff:`line-length = 100`,`select = ["E", "F", "I", "UP", "B"]`,check + format 双绿
- commit 前缀:`feat:` / `fix:` / `docs:`;消息用中文
- 本机无 GPU、无 torch;ApiGenerator 的 replicate 调用一律 mock(`MagicMock`,参照 `tests/test_replicate_gen.py`)
- 不修改:SimulatorGenerator、frontend、平面图路径
- 向后兼容:`ApiGenerator` 默认无 `lora_urls` 时行为不变;`image_provider` 切换逻辑不变
- LoRA 权重文件不入库(公网 URL 引用)
- 设计文档 `docs/superpowers/specs/2026-08-11-milestone3.5-lora-web-integration-design.md` 为唯一需求来源,若实现需偏离须先经用户批准

---

### Task 1: ApiGenerator 支持 lora_urls 注入

**Files:**
- Modify: `generation/generators/api/replicate_gen.py:35-59`
- Test: `tests/test_replicate_gen.py`

**Interfaces:**
- Consumes: 现有 `SDXL_MODEL`、`CONTROLNET_TYPE`、`CONTROLNET_STEPS`、`CONTROLNET_GUIDANCE` 常量
- Produces:
  - `ApiGenerator.__init__(self, replicate_client=None, model: str = SDXL_MODEL, lora_urls: dict[str, str] = {})`
  - `ApiGenerator._call_sdxl(self, prompt, control_image, out_path, lora_url: str | None = None) -> None` — 非 None 时 input 注入 `"lora_weights": lora_url`
  - `ApiGenerator._render_facade_sdxl(self, params, scheme_id, out_dir, lang)` — 按 `params.style` 从 `self._lora_urls` 查 URL,查不到传 None

- [ ] **Step 1: 写失败测试(追加到 tests/test_replicate_gen.py 末尾)**

```python
@pytest.mark.asyncio
async def test_generate_injects_lora_when_configured(tmp_path: Path):
    """配置了 lora_urls 且风格命中 → client.run 收到 lora_weights=<url>。"""
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

    kwargs = client.run.call_args.kwargs
    assert kwargs["input"]["lora_weights"] == "https://cdn.example.com/lora/modern.tar"


@pytest.mark.asyncio
async def test_generate_no_lora_when_unconfigured(tmp_path: Path):
    """未配置 lora_urls → client.run 不收 lora_weights(向后兼容)。"""
    client, real = _make_client(tmp_path)
    with patch(
        "generation.generators.api.replicate_gen.urllib.request.urlretrieve",
        side_effect=lambda url, dest: __import__("shutil").copyfile(url, dest),
    ):
        gen = ApiGenerator(replicate_client=client)
        await gen.generate(_params(), "sid-l2", tmp_path, "zh")

    assert "lora_weights" not in client.run.call_args.kwargs["input"]


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

    assert "lora_weights" not in client.run.call_args.kwargs["input"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_replicate_gen.py -v`
Expected: 新增 3 个测试 FAIL(AttributeError / lora_weights 不存在)

- [ ] **Step 3: 实现最小改动**

```python
    def __init__(self, replicate_client=None, model: str = SDXL_MODEL, lora_urls: dict[str, str] = {}):
        if replicate_client is None:
            raise ApiGeneratorError("replicate client not provided (set replicate_api_token)")
        self._client = replicate_client
        self._model = model
        self._lora_urls = lora_urls

    def _call_sdxl(self, prompt: str, control_image: Path, out_path: Path, lora_url: str | None = None) -> None:
        """Synchronous Replicate ControlNet SDXL call (runs in thread pool)."""
        sdxl_input = {
            "prompt": prompt,
            "negative_prompt": build_negative_prompt(),
            "image": f,
            "model_type": CONTROLNET_TYPE,
            "num_inference_steps": CONTROLNET_STEPS,
            "guidance_scale": CONTROLNET_GUIDANCE,
            "seed": 42,
        }
        if lora_url is not None:
            sdxl_input["lora_weights"] = lora_url
        with open(control_image, "rb") as f:
            output = self._client.run(self._model, input=sdxl_input)
```

注意:Step 3 只展示改动轮廓,`input` 字典需在 `open(control_image)` 上下文内构造(现有 `image: f` 依赖文件对象在 with 块内打开),实现时保持原 `with open(...)` 结构、把 `lora_url` 条件注入放进 `input={...}` 构造处即可。

`_render_facade_sdxl` 中 `_call_sdxl` 调用改为:

```python
        await asyncio.to_thread(
            self._call_sdxl,
            prompt,
            control,
            out_dir / FACADE_FILE,
            self._lora_urls.get(params.style),
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_replicate_gen.py -v`
Expected: 全部 PASS(3 新增 + 3 原有)

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check generation/generators/api/replicate_gen.py tests/test_replicate_gen.py && uv run ruff format --check generation/generators/api/replicate_gen.py tests/test_replicate_gen.py`
Expected: 无告警
Run: `uv run ruff format generation/generators/api/replicate_gen.py tests/test_replicate_gen.py && uv run ruff check generation/generators/api/replicate_gen.py tests/test_replicate_gen.py`
Expected: 双绿

```bash
git add generation/generators/api/replicate_gen.py tests/test_replicate_gen.py
git commit -m "feat: ApiGenerator 支持按风格注入 LoRA 权重(lora_urls 查表,缺省降级)"
```

---

### Task 2: Settings 新增 sdxl_model 与 lora_weights_dir 字段

**Files:**
- Modify: `backend/app/core/config.py:6-14`

**Interfaces:**
- Consumes: 无(纯新增字段)
- Produces:
  - `Settings.sdxl_model: str = ""` — 带 LoRA 的模型名,空=用默认 `SDXL_MODEL`
  - `Settings.lora_weights_dir: str = ""` — 风格 LoRA 权重公网 URL 目录,空=不注入

- [ ] **Step 1: 写失败测试(追加到 tests/test_replicate_gen.py 末尾)**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_replicate_gen.py::test_settings_lora_fields_default_empty tests/test_replicate_gen.py::test_settings_lora_fields_can_be_set -v`
Expected: 2 个 FAIL(ValidationError: 未知字段被 extra="ignore" 丢弃,断言取不到属性)

- [ ] **Step 3: 实现**

在 `Settings` 类中 `image_provider` 之后追加两个字段(紧跟 replicate 相关配置):

```python
    sdxl_model: str = ""          # 带 LoRA 的模型名,空=用默认 SDXL_MODEL
    lora_weights_dir: str = ""    # 风格 LoRA 权重公网 URL 目录,空=不注入
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_replicate_gen.py::test_settings_lora_fields_default_empty tests/test_replicate_gen.py::test_settings_lora_fields_can_be_set -v`
Expected: 2 个 PASS

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check backend/app/core/config.py tests/test_replicate_gen.py && uv run ruff format backend/app/core/config.py tests/test_replicate_gen.py && uv run ruff check backend/app/core/config.py tests/test_replicate_gen.py`
Expected: 双绿

```bash
git add backend/app/core/config.py tests/test_replicate_gen.py
git commit -m "feat: Settings 新增 sdxl_model 与 lora_weights_dir 配置字段"
```

---

### Task 3: generate.py replicate 分支组装 lora_urls 并传模型名

**Files:**
- Modify: `backend/app/api/generate.py:31-38`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes:
  - `Settings.sdxl_model`、`Settings.lora_weights_dir`(Task 2)
  - `ApiGenerator(replicate_client=..., model=..., lora_urls=...)`(Task 1)
  - `generation.generators.api.replicate_gen.SDXL_MODEL` 常量(import)
- Produces: replicate 分支按配置构造带 `lora_urls`/`model` 的 `ApiGenerator`

- [ ] **Step 1: 写失败测试(追加到 tests/test_api.py 末尾)**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_api.py::test_generate_replicate_injects_lora_and_model -v`
Expected: FAIL(`lora_urls` 不在 call_args.kwargs 中)

- [ ] **Step 3: 实现**

`generate.py` 顶部 import 区追加 `from generation.generators.api.replicate_gen import SDXL_MODEL`(放在现有 `from generation.generators.api import ApiGenerator` 之后)。replicate 分支改为:

```python
    if settings.image_provider == "replicate":
        if not settings.replicate_api_token:
            raise HTTPException(status_code=500, detail="replicate_api_token 未配置")
        import replicate

        lora_urls = {}
        if settings.lora_weights_dir:
            lora_urls = {
                style: f"{settings.lora_weights_dir}/{style}.tar"
                for style in STYLE_NAMES
            }
        generator = ApiGenerator(
            replicate_client=replicate.Client(token=settings.replicate_api_token),
            model=settings.sdxl_model or SDXL_MODEL,
            lora_urls=lora_urls,
        )
```

`STYLE_NAMES` 从 `generation.params.model` import(现有 `BuildingParams` 已从该模块引入,合并到同一 import 语句)。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_api.py -v`
Expected: 新增测试 PASS,原有测试(含 `test_generate_uses_apigenerator_when_replicate`)仍 PASS

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check backend/app/api/generate.py tests/test_api.py && uv run ruff format backend/app/api/generate.py tests/test_api.py && uv run ruff check backend/app/api/generate.py tests/test_api.py`
Expected: 双绿

```bash
git add backend/app/api/generate.py tests/test_api.py
git commit -m "feat: replicate 分支按 lora_weights_dir 组装风格 LoRA URL 并传配置模型名"
```

---

### Task 4: 全量回归 + smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`

**Interfaces:**
- Consumes: Task 1-3 全部改动
- Produces: 冒烟验证记录

- [ ] **Step 1: 全量测试 + ruff 双绿**

Run: `uv run pytest -v`
Expected: 82(原有)+ 3(Task1)+ 2(Task2)+ 1(Task3)= **88 passed + 1 skipped**(`test_training_skip.py` 本机无 torch 跳过)
Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 双绿

- [ ] **Step 2: 真调前置检查(仅当 token 与公网 URL 可用)**

检查 `.env` 是否有 `REPLICATE_API_TOKEN`(gitignored);检查公网 LoRA URL 是否可达(如 `curl -I https://cdn.example.com/lora/modern.tar`)。
- 若两项均可用:记录真调结果到 smoke-test.md(模型名、风格、是否收到 lora_weights、出图是否更贴风格、耗时)
- 若任一不可用:在 smoke-test.md 记录「真调留待人工:需 REPLICATE_API_TOKEN + 公网权重 URL(tar 打包,内含 lora.safetensors)」,代码落地 + mock 绿即视为本期完成

- [ ] **Step 3: smoke-test.md 追加里程碑3.5 记录**

```markdown
# 里程碑 3.5 LoRA 接入网页验证记录 (2026-08-11)

- ApiGenerator 支持 lora_urls(风格→公网 URL),命中风格注入 lora_weights,缺省降级不注入
- Settings 新增 sdxl_model / lora_weights_dir;replicate 分支按 {dir}/{style}.tar 组装
- mock 单测:配置注入 / 未配置不注入 / 风格缺失降级 3 例 + Settings 字段 2 例 + 路由组装 1 例
- 全量回归: 88 passed + 1 skipped;ruff check + format 双绿
- 真调:<结果或留待人工,记录 token/公网 URL 可用性>
```

- [ ] **Step 4: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 里程碑3.5 LoRA 接入验证记录(全量回归 + 真调状态)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| `ApiGenerator.__init__` 加 `lora_urls: dict[str,str]={}` | Task 1 | 测试 + ruff |
| `_call_sdxl` 加 `lora_url` 可选注入 `lora_weights` | Task 1 | `test_generate_injects_lora_when_configured` |
| `_render_facade_sdxl` 按 style 查表,查不到降级 | Task 1 | `test_generate_lora_missing_style_falls_back` |
| 模型默认仍 `SDXL_MODEL` | Task 1/3 | `model` 参数缺省 |
| `Settings.sdxl_model` / `Settings.lora_weights_dir` | Task 2 | 默认空 / 可设置 |
| replicate 分支组装 lora_urls + 传模型名 | Task 3 | `test_generate_replicate_injects_lora_and_model` |
| 真调验证(需 token + 公网 URL) | Task 4 | smoke-test.md 记录 |
| 不修改 SimulatorGenerator/frontend/平面图 | 全计划 | diff 检查 |
| 向后兼容(默认无 lora_urls 行为不变) | Task 1/3 | 原有测试仍绿 |
