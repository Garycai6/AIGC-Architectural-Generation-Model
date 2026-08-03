# 建筑 AIGC 生成模型 — 里程碑1：网页产品框架设计

日期：2026-08-04
状态：已确认

## 背景与定位

建筑 AIGC 生成模型项目：通过 Stable Diffusion/Transformer 微调，输入建筑参数（风格/体量/材质/场地），自动生成建筑方案（效果图 + 平面图）。最终交付为网页形式的 Freemium SaaS，面向非专业公众，中英双语兼顾。

本机 GPU 仅 2GB 显存，无法训练/推理 SDXL，所有训练与推理须在云端（RunPod/AutoDL/Fal）进行。本机只负责前后端开发与数据清洗。

## 总体路线（里程碑序列）

```
里程碑1  网页产品框架（最小闭环，模拟器出图）  ← 当前
里程碑2  数据资产（建筑立面/平面图收集与清洗）
里程碑3  云端训练管线（SDXL + LoRA + ControlNet）
里程碑4  接入真实模型，替换模拟器
里程碑5  商业化（账号/额度/订阅，Freemium）
```

核心逻辑：先固定产品形态，再为它填上模型。模型训练贵、慢、不可控，产品框架是本机即可推进的部分。

## 里程碑1 功能边界（最小闭环）

- 用户填参数表单：风格 / 体量 / 材质 / 场地
- 点击"生成" → 后端接收 → 模拟器返回结果图
- 展示生成结果（效果图 + 平面图，双产出占位）
- 无登录、无支付、无历史记录

## 技术方案

- FastAPI 后端 + Jinja2 模板 + HTMX（轻前端，少写 JS）
- 模拟器：根据参数确定性/伪随机生成占位图（组合色块、几何占位），输出到结果页
- 数据模型：`DesignRequest`（参数）→ `GenerationResult`（结果），为日后接入真实模型留好接口边界
- 本机 Python 3.11.15 + venv，`uvicorn` 本地运行

## 关键设计决策：生成后端接口边界

模拟器与真实模型共享同一接口契约，网页层只认：

```
DesignRequest (风格/体量/材质/场地) → GenerationResult (效果图 + 平面图)
```

将来真实模型（SDXL+LoRA+ControlNet）只需实现同一接口，网页层零改动。此为模拟器架构的立足点。

## 目录结构（拟定）

```
AIGC Architectural Generation Model/
├── app/
│   ├── main.py            # FastAPI 入口
│   ├── schemas.py         # DesignRequest / GenerationResult 数据模型
│   ├── generator/         # 生成后端，可插拔
│   │   ├── base.py        # 生成器接口契约
│   │   ├── mock.py        # 模拟器实现
│   │   └── (future: sdxl.py / cloud.py)
│   ├── templates/         # Jinja2 模板
│   └── static/            # CSS/JS
├── docs/superpowers/specs/
└── requirements.txt
```

## 里程碑序列说明

- 里程碑2（数据资产）与里程碑3（训练管线）可并行推进准备。
- 里程碑5（商业化）在真实模型接入、效果验证后再做。
