# 建筑 AIGC 生成模型 — ApiGenerator 异步 prediction 改造设计

日期:2026-08-11
状态:已确认

## 背景与定位

里程碑3 真调时发现 `ApiGenerator` 用 `client.run` 同步调 SDXL,两次调用慢且 create 请求的 read timeout 默认仅 60.5s(SDK `_create_prediction_timeout`: `wait=True` → read=60.5),真调曾需手动配 `timeout=300`。本期把 SDXL 调用改异步 prediction,消除线程池占用、解除 60s 超时,作为生产前置项。

## 关键事实(调研确认)

- replicate SDK 1.0.7 内置异步能力:
  - `Client.async_run(model, input, wait=...)` — 内部就是 `predictions.async_create` + `prediction.async_wait()`(异步轮询:`asyncio.sleep(poll_interval)` + `async_reload`,默认 poll 0.5s)
  - `async_wait` 轮询直到 status ∈ {succeeded, failed, canceled}
  - 传 `wait=<秒数>` 会把 create 请求 read timeout 扩到 `<秒数>+0.5`;即使请求超时,SDK 仍 fallback 到 `async_wait()` 继续轮询
- 当前实现 `_call_sdxl` 是同步 `client.run` 包在 `asyncio.to_thread`(占线程池,非真正异步)

## 架构

```
ApiGenerator._render_facade_sdxl (async)
  └── await _call_sdxl(...)                    # async,不再 to_thread
        └── client.async_run(model, input, wait=300)   # SDK 内置异步轮询
```

## 组件改动

### 1. `generation/generators/api/replicate_gen.py`

- 新增常量 `SDXL_WAIT_SECONDS = 300`(对齐真调验证时手动配的 timeout=300)
- `_call_sdxl` 改 `async def`,签名不变 `(prompt, control_image, out_path, lora_url=None) -> None`;内部 `client.run(self._model, input=sdxl_input)` → `await self._client.async_run(self._model, input=sdxl_input, wait=SDXL_WAIT_SECONDS)`
- `_render_facade_sdxl` 里 `await asyncio.to_thread(self._call_sdxl, prompt, control, out, self._lora_urls.get(...))` → `await self._call_sdxl(prompt, control, out, self._lora_urls.get(...))`
- 若 `import asyncio` 无其他用途则删除(仅 `_render_facade_sdxl` 用过)
- 文件 URL 提取(`output[-1]`)、`lora_weights` 注入、风格降级逻辑**全部不变**

### 2. `tests/test_replicate_gen.py`

- `_make_client` 的 mock 由 `client.run` 改为 `client.async_run`(`AsyncMock`,返回 `[edge, real]` 路径)
- 3 个 LoRA 注入测试 + `test_generate_calls_replicate_once` 改为断言 `async_run`
- 新增 1 例:`async_run` 收到 `wait=300`
- `urlretrieve` mock 保持不变(仍是 `urllib.request.urlretrieve`)

### 3. `backend/app/api/generate.py`

- `replicate.Client(token=...)` 构造不变(create 请求超时由 `wait=300` 覆盖,无需显式配 timeout)

## 测试策略

- mock 单测(本机无 GPU、无真调):
  - `async_run` 被调用 1 次(facade only)
  - 配置 lora_urls 时 `async_run` input 含 `lora_weights=<style_url>`
  - 未配置时 input 不含 `lora_weights`(向后兼容)
  - 风格缺失降级不注入
  - `async_run` 收到 `wait=300`
- 真调验证:手动,需 token + 公网 URL,记录到 smoke-test.md

## 交付边界

- 代码:`ApiGenerator` SDXL 调用改 `async_run`(wait=300)+ 测试改造
- 验证:mock 测试绿 + 全量回归 + ruff 双绿
- 产物:真调场景不再因 60s read timeout 中断;不占线程池

## 与现有代码关系

- 不改:config、SimulatorGenerator、frontend、平面图路径、lora_urls 组装
- 向后兼容:`ApiGenerator.generate()` 对外签名不变,仅内部 SDXL 调用改异步;`image_provider` 切换逻辑不变
- 不引入新依赖(replicate 已是依赖)
