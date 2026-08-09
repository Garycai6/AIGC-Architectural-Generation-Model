# 阶段 3:API 生成器(SDXL + ControlNet)— 设计规格

日期：2026-08-05
状态：已确认
前置：阶段 0/2/2.5 已合并到 master(Generator 协议 + 模拟器线稿 + 写实屋顶/四风格)

## 背景与定位

阶段 0 定下验证期技术路线:「API 优先验证 → 后期微调降本」。Generator 协议抽象(`base.py`)在阶段 2 已建立,`Settings` 预留了 `image_provider`/`replicate_api_token` 字段但从未被消费。阶段 2.5 让模拟器线稿(护城河)质量显著提升。

本阶段目标:**实现 `ApiGenerator` 走通验证期真实模型链路**——模拟器线稿作为 ControlNet 条件图,驱动 Replicate SDXL 出真图。效果图与平面图都走真模型。护城河(程序化线稿)由此获得第二重角色:自己出占位图 + 喂真实模型。

## 关键决策(已确认)

| 决策点 | 结论 |
|---|---|
| 出图路线 | SDXL + ControlNet,模拟器线稿作条件图 |
| 双产出 | 效果图与平面图都走真模型(SDXL+ControlNet × 2) |
| 验证深度 | 实现 + mock 测试(确定性零成本)+ 真调一次验证 |
| 选择策略 | 全局 provider 配置(`Settings.image_provider`),模拟器默认 |
| prompt 来源 | 程序化「参数→prompt」模块(护城河),支持 facade/floorplan 两类 |
| 平面图风险 | SDXL 对建筑平面图生成质量可能不理想(训练数据少),ControlNet 约束结构;验证期实测 |

## 架构

```
generation/generators/
├── base.py              # 已有:Generator 协议 + GenerationArtifact + ImageRef
├── simulator/           # 已有:SimulatorGenerator + facade/floorplan 线稿渲染
└── api/
    ├── __init__.py      # 导出 ApiGenerator
    ├── prompt.py        # 参数→SDXL prompt(护城河:确定性、双类 facade/floorplan)
    └── replicate_gen.py # ApiGenerator:Replicate SDXL + ControlNet
```

## 组件职责

### prompt.py(护城河,确定性)

- `def build_prompt(params: BuildingParams, kind: Literal["facade", "floorplan"], lang: str = "en") -> str`
  - facade:风格/材质/环境/屋顶/体量 → SDXL 建筑立面 prompt 模板
  - floorplan:强调「建筑平面图/户型图」+ 体量 → 平面 prompt 模板
  - SDXL 对英文 prompt 效果最佳,固定输出英文(即使 lang=zh 也出英文 prompt)
- `def build_negative_prompt() -> str`:低质量/变形/水印等负面 prompt
- 确定性、纯代码,与线稿互补,同属护城河

### replicate_gen.py

- `class ApiGenerator` 实现 `Generator` 协议:`async def generate(self, params, scheme_id, out_dir, lang="zh") -> GenerationArtifact`
- `generate` 流程:
  1. 复用 `render_scheme` 生成 facade 线稿 + floorplan 线稿(作为两条 ControlNet 条件图)
  2. `build_prompt(params, "facade")` → 第 1 次 SDXL 调用(facade 线稿作条件图)
  3. `build_prompt(params, "floorplan")` → 第 2 次 SDXL 调用(floorplan 线稿作条件图)
  4. 两个真图 PNG 落盘 `out_dir`(覆盖线稿),返回 `GenerationArtifact`
- 内部用 Replicate SDK:`replicate.run(model, input={prompt, negative_prompt, control_image, ...})`
- 无 API key 时初始化抛配置错误;调用失败/超时抛 `ReplicateError`

## 数据流

```
BuildingParams → ApiGenerator.generate
  ├─ render_scheme → facade 线稿 + floorplan 线稿(条件图)
  ├─ build_prompt(facade) → SDXL#1 + ControlNet(立面线稿)
  ├─ build_prompt(floorplan) → SDXL#2 + ControlNet(平面线稿)
  └─ 两个真图 PNG 落盘 out_dir
  → GenerationArtifact { facade: 真效果图, floorplan: 真平面图 }
```

## 路由切换(全局 provider 配置)

`backend/app/api/generate.py` 的 `generate` 路由,按 `Settings.image_provider` 选生成器:
- `"simulator"`(默认)→ `SimulatorGenerator`
- `"replicate"` → `ApiGenerator`

## 错误处理

- Replicate 调用失败/超时 → `HTTPException(502/504)` + 结构化错误,前端显示可读消息
- 无 `replicate_api_token` 时 `ApiGenerator` 初始化抛配置错误
- 生成产物仍落盘 `cache_dir`,gitignored

## 测试策略

- **mock 测试(确定性零成本)**:
  - mock Replicate 客户端(`unittest.mock.patch`),断言 `ApiGenerator.generate` 产出 artifact、落盘 2 个真图、按序调用 SDXL × 2
  - prompt 测试:不同参数生成不同 prompt,关键元素(风格/材质/环境/kind)在 prompt 中
  - 路由测试:`image_provider` 切换生成器(mock)
- **真调一次验证**:真实 Replicate 调用(需 API key),记入冒烟文档
- 现有 45 测试全部保持通过(regression)

## 明确排除(本阶段不做)

- ❌ 前端不改(仍走 API,`images` 契约不变,零前端改动)
- ❌ 额度 / 计费 / 历史 / 登录
- ❌ 多供应商抽象(本阶段仅 Replicate;Fal 后续按同协议加)
- ❌ prompt 用 DeepSeek 生成(纯程序化,保持护城河确定性)

## 对既有约束的遵守

- 护城河代码(`prompt.py` + 线稿)不依赖模型供应商,验证期与稳定期共用
- `Generator` 协议不变,网页层零改动
- 确定性 mock 测试(不真调 API 的测试全部离线);真调验证单独标记
- uv 管理依赖(replicate 已在 pyproject.toml);ruff lint + pytest 全绿
- 提交信息 `feat:` / `fix:` 前缀
