# ApiGenerator 异步 prediction 改造 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ApiGenerator 的 SDXL 调用从同步 `client.run`(包在 `asyncio.to_thread`)改为异步 `client.async_run(model, input, wait=300)`,解除 60s read timeout、不占线程池。

**Architecture:** 用 replicate SDK 1.0.7 内置的 `async_run`(内部即 `async_create` + `prediction.async_wait()` 异步轮询)。`_call_sdxl` 改为 `async def`,`_render_facade_sdxl` 直接 `await`,删除 `asyncio.to_thread`。测试 mock 从 `client.run` 改为 `client.async_run`。

**Tech Stack:** Python 3.11 / replicate SDK 1.0.7 / pytest(MagicMock + AsyncMock)+ ruff(E/F/I/UP/B)。

## Global Constraints

- ruff:`line-length = 100`,`select = ["E", "F", "I", "UP", "B"]`,check + format 双绿
- commit 前缀:`feat:` / `fix:` / `docs:`;消息用中文
- 本机无 GPU、无 torch;replicate 调用一律 mock
- 不改:`backend/app/api/generate.py`、config、SimulatorGenerator、frontend、平面图路径
- 向后兼容:`ApiGenerator.generate()` 对外签名不变,仅内部 SDXL 调用改异步
- 设计文档 `docs/superpowers/specs/2026-08-11-apigenerator-async-prediction-design.md` 为唯一需求来源

---

### Task 1: ApiGenerator 改用 async_run 异步调用

**Files:**
- Modify: `generation/generators/api/replicate_gen.py:16-84`
- Test: `tests/test_replicate_gen.py`

**Interfaces:**
- Consumes: 现有 `SDXL_MODEL`、`CONTROLNET_TYPE`、`CONTROLNET_STEPS`、`CONTROLNET_GUIDANCE`、`FACADE_FILE` 常量
- Produces:
  - 新常量 `SDXL_WAIT_SECONDS = 300`
  - `ApiGenerator._call_sdxl(prompt, control_image, out_path, lora_url=None) -> None` 改为 **`async def`**,内部 `await self._client.async_run(self._model, input=sdxl_input, wait=SDXL_WAIT_SECONDS)`
  - `ApiGenerator._render_facade_sdxl(params, scheme_id, out_dir, lang)` 直接 `await self._call_sdxl(...)`,不再 `to_thread`
  - 若 `import asyncio` 无其他用途则删除

- [ ] **Step 1: 写失败测试(先改 _make_client + 相关断言,再新增 wait 测试)**

将 `_make_client` 从同步 mock 改为 async mock(用 `AsyncMock`,普通 MagicMock 的返回值不可被 `await`):

```python
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
```

同时把测试文件顶部 import 改为:

```python
from unittest.mock import AsyncMock, MagicMock, patch
```

将 `test_generate_calls_replicate_once` 的断言改为 `async_run`:

```python
    # one SDXL call (facade only), through the injected client
    assert client.async_run.call_count == 1
```

将 3 个 LoRA 测试的 `client.run.call_args.kwargs` 改为 `client.async_run.call_args.kwargs`(共 3 处)。

在文件末尾追加新增测试:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_replicate_gen.py -v`
Expected: 失败——`_call_sdxl` 仍是同步 `client.run`,`client.async_run` 从未被调用 → `test_generate_async_run_waits_300` 与改造后的断言失败;同时 `test_generate_calls_replicate_once` 断言 `async_run.call_count == 1` 实际为 0 而失败

- [ ] **Step 3: 实现**

在常量区(`FACADE_FILE` 之后)新增:

```python
SDXL_WAIT_SECONDS = 300
```

`_call_sdxl` 改为:

```python
    async def _call_sdxl(
        self,
        prompt: str,
        control_image: Path,
        out_path: Path,
        lora_url: str | None = None,
    ) -> None:
        """Asynchronous Replicate ControlNet SDXL call (SDK polls internally)."""
        with open(control_image, "rb") as f:
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
            output = await self._client.async_run(
                self._model, input=sdxl_input, wait=SDXL_WAIT_SECONDS
            )
        # output is a list of file URLs; the last item is the real generated
        # image (earlier items are ControlNet condition/edge maps).
        file_url = output[-1] if isinstance(output, list) else output
        urllib.request.urlretrieve(str(file_url), str(out_path))
```

`_render_facade_sdxl` 改为:

```python
    async def _render_facade_sdxl(self, params, scheme_id, out_dir, lang) -> None:
        """Facade goes through SDXL + ControlNet (facade_line.png is the
        condition image); floorplan stays the simulator line-art."""
        prompt = build_prompt(params, "facade", lang)
        control = out_dir / "facade_line.png"
        await self._call_sdxl(
            prompt, control, out_dir / FACADE_FILE, self._lora_urls.get(params.style)
        )
```

若 `import asyncio` 在文件中不再被任何代码使用,删除该 import(run: `uv run ruff check generation/generators/api/replicate_gen.py`,若报 F401 未使用则删;若其他代码用了则保留)。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_replicate_gen.py -v`
Expected: 全部 PASS(3 原有 + 4 LoRA/Settings 相关 + 1 新增 wait = 8 个)

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check generation/generators/api/replicate_gen.py tests/test_replicate_gen.py && uv run ruff format generation/generators/api/replicate_gen.py tests/test_replicate_gen.py && uv run ruff check generation/generators/api/replicate_gen.py tests/test_replicate_gen.py`
Expected: 双绿

```bash
git add generation/generators/api/replicate_gen.py tests/test_replicate_gen.py
git commit -m "feat: ApiGenerator 改用 async_run 异步 prediction(wait=300 解除超时)"
```

---

### Task 2: 全量回归 + smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`

**Interfaces:**
- Consumes: Task 1 全部改动
- Produces: 冒烟验证记录

- [ ] **Step 1: 全量测试 + ruff 双绿**

Run: `uv run pytest -q`
Expected: 88 passed + 1 skipped(数量不变——仅改造,无新增测试文件;`test_generate_async_run_waits_300` 算入 88 内的替换而非新增)
Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 双绿

- [ ] **Step 2: 真调前置检查(仅当 token 与公网 URL 可用)**

检查 `.env` 是否有 `REPLICATE_API_TOKEN`;检查公网 LoRA URL 是否可达。
- 若可用:真调一次 `image_provider=replicate`,确认 `async_run` 链路通、出图正常,记录到 smoke-test.md
- 若不可用:记录「真调留待人工」(本轮改造仅 mock 验证,真调需 token + 公网权重 URL)

- [ ] **Step 3: smoke-test.md 追加记录**

```markdown
# ApiGenerator 异步 prediction 改造验证记录 (2026-08-11)

- _call_sdxl 改 async,用 client.async_run(model, input, wait=300) 替代同步 client.run + to_thread
- SDK 内置异步轮询(async_create + prediction.async_wait),wait=300 解除 create 请求 60s read timeout
- mock 单测:async_run 调用 1 次、lora_weights 注入/降级逻辑不变、wait=300 断言
- 全量回归: 88 passed + 1 skipped;ruff check + format 双绿
- 真调:<结果或留待人工>
```

- [ ] **Step 4: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: ApiGenerator 异步 prediction 改造验证记录(全量回归 + 真调状态)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| `_call_sdxl` 改 async,`client.run` → `await client.async_run(model, input, wait=300)` | Task 1 | `test_generate_async_run_waits_300` |
| 新增 `SDXL_WAIT_SECONDS = 300` 常量 | Task 1 | 实现步骤 |
| `_render_facade_sdxl` 不再 `to_thread` | Task 1 | 实现步骤 |
| `import asyncio` 无用则删 | Task 1 | ruff F401 |
| lora_urls 注入 / 降级逻辑不变 | Task 1 | 3 个 LoRA 测试仍绿 |
| mock 测试改造(`client.run` → `async_run`) | Task 1 | 全部测试 |
| 真调验证 | Task 2 | smoke-test.md 记录 |
| 不碰 generate.py/config/SimulatorGenerator/frontend | 全计划 | diff 检查 |
| `ApiGenerator.generate()` 对外签名不变 | 全计划 | 原有测试仍绿 |
