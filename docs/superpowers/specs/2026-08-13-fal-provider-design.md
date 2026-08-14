# 多供应商 Fal 设计规格

> 日期:2026-08-13
> 状态:已批准
> 目标:在 Replicate 之外接入 Fal 作为图片生成供应商,降低供应商锁定风险(Replicate 社区模型曾 404),实现供应商间成本/质量对比。

## 背景与动机

验证期图片生成走 Replicate(阶段 3 真调已验证),但已观察过一次真实风险:`jagilley/controlnet-sdxl` 社区模型 404,被迫换成 `replicategithubwc/controlnet-sdxl`——社区模型随时可能下线。Fal 作为第二供应商是对这个已观察风险的直接对冲,也是项目「生成适配器抽象、供应商无缝切换」架构理念的自然延伸。

## 需求(已与用户确认)

| 决策点 | 结论 |
|---|---|
| 生成范围 | facade-only,与 replicate 一致(floorplan 保持模拟器线稿,SDXL 不适合平面图已真调证实) |
| LoRA 注入 | 本期不做(fal 的 loras 参数格式与 replicate 不同,对齐时再做) |
| 模型 | `fal-ai/fast-sdxl-controlnet-canny`(与 replicate 的 controlnet-sdxl canny 对等,对比才公平) |
| SDK | 正式依赖 `fal-client`(轻量,提供 async queue + upload_file) |
| 架构 | 方案 A:独立 `FalGenerator` 类 + Settings 加 fal 配置(供应商隔离,互不掣肘) |

## 架构

### 组件

**1. `generation/generators/api/fal_gen.py`(新建)— `FalGenerator`**

- 常量:`FAL_MODEL = "fal-ai/fast-sdxl-controlnet-canny"`;`CONTROLNET_CONDITIONING_SCALE = 0.5`(与 replicate 的 condition_scale 0.5 对齐);`FAL_STEPS = 30`;`FAL_GUIDANCE = 7.5`;`FAL_WAIT_SECONDS = 300`(传给 `submit_async` 的 `start_timeout`,限制排队+处理总时长,与 replicate 的 wait=300 对称)
- `FalGeneratorError(Exception)` — 与 `ApiGeneratorError` 对称
- `FalGenerator.__init__(self, fal_client=None, model: str = FAL_MODEL)` — fal_client 缺失抛 `FalGeneratorError`(与 ApiGenerator 同风格)
- `_upload_lineart(path: Path) -> str` — `fal_client.upload_file(path)` 返回公网 URL
- `_call_fal(prompt, control_url, out_path) -> None` — `submit_async(FAL_MODEL, arguments=...)` → `iter_events` 等 `Completed` → `get()` → `images[0]["url"]` → `urllib.request.urlretrieve` 落盘
  - arguments:`{"prompt": prompt, "negative_prompt": build_negative_prompt(), "control_image_url": control_url, "controlnet_conditioning_scale": CONTROLNET_CONDITIONING_SCALE, "num_inference_steps": FAL_STEPS, "guidance_scale": FAL_GUIDANCE, "image_size": {"width": 1024, "height": 1024}, "num_images": 1, "seed": 42}`
- `generate(params, scheme_id, out_dir, lang) -> GenerationArtifact` — 与 ApiGenerator 同骨架:render_scheme → facade 线稿重命名 `facade_line.png` → 上传 → SDXL → 清理条件图 → artifact(facade 真图 + floorplan 模拟器线稿)

**2. `backend/app/core/config.py`** — 加 2 字段:

```python
fal_api_key: str = ""  # fal 密钥,空=不可用
fal_model: str = ""    # fal 模型名,空=用默认 FAL_MODEL
```

**3. `backend/app/api/generate.py`** — `image_provider` 加 `"fal"` 分支:

```python
elif settings.image_provider == "fal":
    if not settings.fal_api_key:
        raise HTTPException(status_code=500, detail="fal_api_key 未配置")
    import fal_client
    generator = FalGenerator(
        fal_client=fal_client,
        model=settings.fal_model or FAL_MODEL,
    )
```

**4. `pyproject.toml`** — 加 `fal-client` 依赖。

### 关键设计点

- **与 replicate 分支对称**:路由显式分支,行为对齐(simulator 默认、无 token 500、facade-only)
- **`prompt.py` 零改动**:`build_prompt`/`build_negative_prompt` 供应商无关,直接复用
- **`Generator` 协议零改动**:`FalGenerator.generate` 同签名,网页层无感
- **供应商差异**(设计依据):Fal 条件图必须传公网 URL(需 upload_file),Replicate 直接传文件;Fal 输出 `images[0].url`,Replicate 输出列表 `output[-1]`——差异够大,泛化类会互相掣肘,故独立类

## 数据流(一次 fal 生成)

1. 路由 fal 分支:校验 `fal_api_key`(空 → 500)→ 构造 `FalGenerator`
2. `generate()`:`render_scheme` 出模拟器线稿(facade + floorplan)
3. facade 线稿重命名 `facade_line.png`(条件图,同 replicate)
4. `_upload_lineart`:`fal_client.upload_file(facade_line.png)` → fal 存储 URL
5. `_call_fal`:提交 → 等 `Completed` → `get()` → `images[0]["url"]` 下载落盘 `facade.png`
6. 清理 `facade_line.png` → 返回 artifact

## 错误处理

| 场景 | 行为 |
|---|---|
| `fal_api_key` 为空且 provider=fal | HTTP 500「fal_api_key 未配置」(与 replicate 分支同风格) |
| fal 调用失败(超时/队列错误/网络) | `FalGeneratorError` 向上抛,与 replicate 的 `ApiGeneratorError` 对称 |
| 上传失败 | `FalGeneratorError` 向上抛 |
| 下载失败(urlretrieve 异常) | 自然抛出(与 replicate 同行为) |
| provider 非法值 | 现有 else 兜底 simulator(行为不变) |

## 测试策略

| 层级 | 用例 |
|---|---|
| 单元(fal_gen) | mock fal_client:upload_file 被调、submit_async 收到正确 arguments(control_image_url/scale 0.5/steps 30/seed 42)、输出下载到 out_path、facade_line 清理 |
| 单元(prompt) | 现有 prompt 测试零改动(供应商无关,已覆盖) |
| 路由(test_api) | `image_provider="fal"` + token → mock FalGenerator 被调;无 token → 500 |
| Settings | fal_api_key / fal_model 默认空 |
| 回归 | 现有 111 passed + 1 skipped 保持全绿 |

**真调**:留待人工(需 FAL_KEY token),代码落地 + mock 绿即视为本期完成,与 replicate 真调的处理方式一致。

## 明确不做(本期)

- LoRA 注入(fal 的 loras 参数格式与 replicate 不同,对齐时再做)
- 供应商自动故障切换/负载均衡(手动 `image_provider` 切换够用)
- 成本对比报告(真调阶段人工对比即可)
- fal 的 union 模型(比 canny 版复杂,且与 replicate 对比不公平)
- 前端改动(provider 由后端 `.env` 控制,前端无感)
