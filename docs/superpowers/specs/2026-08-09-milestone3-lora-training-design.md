# 建筑 AIGC 生成模型 — 里程碑3:SDXL LoRA 云端训练管线设计

日期:2026-08-09
状态:已确认

## 背景与定位

里程碑2 数据资产已完成:325 张合成图(166 facade + 159 floorplan)+ metadata.jsonl,每张带完整 BuildingParams 标签。里程碑3 是 **LoRA 云端训练管线**,根治效果图细节错误(SDXL 固有幻觉)。

本机 GPU 仅 2GB,无法训练/推理 SDXL;本机负责训练代码开发与逻辑测试,训练在云端(AutoDL 4090)执行。已预留 `pyproject.toml` 的 `gpu` 依赖组(torch/diffusers/accelerate/peft)与 `training` wheel 包。

## 已确认的关键决策

- **目标域**:合成渲染图(先跑通管线,画风优化是后续迭代)
- **训练范围**:只训 SDXL LoRA,ControlNet 用现成 canny 版(不训)
- **LoRA 组织**:4 个独立风格 LoRA(modern/neoclassic/european/nordic)
- **承载**:本仓库 `training/` 包,纯本地可开发测试,云端 `python -m training.train` 执行
- **边界**:本期只出训练代码 + LoRA 产物 + 样例图,**不接网页**(接入是下期任务)

## 数据策略

- 用 **166 张 facade 合成图**训练(floorplan 不参与本期 LoRA,SDXL 不适合平面图)
- 每风格 facade 数据量:modern 41 / neoclassic 44 / nordic 41 / european 40
- **不做 train/val 切分**(数据太小,验证意义有限);改用「训练中周期性生成 checkpoint 样例图」做效果验证
- 图片统一缩放到 SDXL 训练分辨率 **1024×1024**(合成图 640×480,居中缩放 + 画布填充)
- 训练 prompt 复用 `generation.generators.api.prompt.build_prompt(params, "facade", lang)`,可叠加风格 trigger 词

## 包结构

```
training/
├── __init__.py
├── config.py          # 训练配置 CLI 解析(argparse),纯逻辑本机可测
├── dataset.py         # 从 data/datasets/<name>/ 读 imagefolder,构建训练样本
├── train.py           # 训练入口(accelerate + diffusers LoRA 循环),云端跑
├── export.py          # 训练产物 → 每个风格一个 .safetensors 单文件
├── verify.py          # 加载产物,出样例图验证(云端跑)
└── __main__.py        # CLI: python -m training.train / .verify / .export
```

### 分层原则(可测性关键)

- **逻辑与框架分离**:config/dataset/export 的纯逻辑(参数解析、过滤、采样、命名)本机可单测,**不 import diffusers/torch**
- **train/verify 在云端跑**:含 `StableDiffusionXLPipeline`/`peft` 的代码本机不 import,测试用 mock/skip 跳过(与 `replicate_gen` 测试同类模式)

## 训练循环(train.py)

- 加载 SDXL base + peft LoRA;每个风格一次训练运行,共享数据加载
- 默认超参:`resolution=1024`、`train_batch_size=1`、`lr=1e-4`、`max_train_steps` 按数据量(如 `len(data) × 50 epochs`)、周期性生成 validation 样例图
- 数据:`dataset.py` 读 `metadata.jsonl` 按风格过滤 facade 记录,构建 `{"image", "prompt"}` 样本
- 加速:`accelerate` 单卡 config 即跑(4090 单卡)

## 验证(verify.py)

- 加载 base SDXL + 训好的风格 LoRA,`txt2img` 出样例图(无 ControlNet 条件)
- 人工目检:产物是否符合风格预期;效果图细节错误是否随 LoRA 缓解
- 样例图存 `docs/gallery/`

## 测试策略

- 本机单测覆盖:config 解析、dataset 过滤/采样、export 路径命名、prompt 构建(纯逻辑)
- diffusers/torch 相关:测试用 mock/skip 不 import(云端才装)
- 全量回归保持 69 tests 绿 + ruff 双绿

## 交付清单

- `training/` 包(6 模块)+ 测试全绿
- 云端训练可执行:`uv pip install -e ".[gpu,datasets]"` 后 `python -m training.train --dataset synth_demo --style modern --output-dir ...`
- LoRA 产物:4 个 `.safetensors` + 样例图
- 设计文档 + 实施计划存档,不接网页(下期)

## 依赖

- 新增 `datasets` 到 `gpu` 可选依赖组(读 imagefolder)
- 云端安装:`uv pip install -e ".[gpu,datasets]"`
- 本机开发不装 GPU 依赖,仅逻辑单测

## 与现有代码关系

- 复用:`data/synth.py` 产出的 `data/datasets/<name>/metadata.jsonl` 格式;`generation.generators.api.prompt.build_prompt`
- 不修改:`generation/`、`data/`、`backend/` 现有代码(训练只是消费者)
- 下期接入:LoRA `.safetensors` 通过 diffusers `load_lora_weights` 或 Replicate 托管挂到网页生成
