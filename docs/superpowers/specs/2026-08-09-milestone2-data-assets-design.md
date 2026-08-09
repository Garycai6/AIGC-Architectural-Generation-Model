# 建筑 AIGC 生成模型 — 里程碑2:数据资产管线设计

日期:2026-08-09
状态:已确认

## 背景与定位

里程碑1(网页产品框架)已完成:参数表单 → 模拟器/真模型生成 → 结果展示,中英双语。里程碑2 是为里程碑3(LoRA + ControlNet 云端训练)准备数据资产。

本机 GPU 仅 2GB 显存,无法训练/推理 SDXL;本机负责数据管线开发与数据清洗,训练在云端(AutoDL/RunPod/Fal)。

## 已确认的关键决策

- **数据来源**:混合(公开数据 + 模拟器合成)
- **规模策略**:小样本起步,先跑通管线
- **推进顺序**:先合成后公开(本机 GitHub/下载网络不稳,合成数据零网络依赖)
- **交付边界**:数据管线 + 小样本数据,公开下载器只定契约不写代码

## 数据集格式(类 HuggingFace imagefolder)

```
data/datasets/<name>/
├── images/                      # 所有图片扁平存放
│   ├── synth_000001.png
│   ├── synth_000002.png
│   └── ...
└── metadata.jsonl               # 每张图一行 JSON
```

`metadata.jsonl` 每行一个记录:

```json
{
  "id": "synth_000001",
  "image": "images/synth_000001.png",
  "source": "synth",
  "kind": "facade",
  "params": {
    "style": "modern", "floors": 2, "width_m": 12.0,
    "depth_m": 9.0, "materials": ["brick"], "roof": "flat",
    "environment": "suburb", "view_angle": "front"
  },
  "width_px": 640,
  "height_px": 480,
  "created_at": "2026-08-09"
}
```

### 格式要点

- **扁平 images/ + 外部索引**:清洗/去重/切分后文件会移动,metadata.jsonl 是唯一事实源,训练脚本无需扫描目录。
- **`kind` 区分 facade/floorplan**:里程碑3 的 ControlNet 训练需要「线稿↔真图」配对;合成 facade 是程序化线稿,天然可作 Canny 条件图。同一组参数产出的 facade 与 floorplan 两条记录都携带同一份完整 `params` 快照,仅 `id`/`image`/`kind`/`width_px`/`height_px` 不同。
- **`source` 区分 synth/web**:合成数据带完整 `params` 标签;公开数据将来无完整参数,只带部分标签(如 style)。用 `source` 区分标注完整度。
- 一个数据集目录同时服务里程碑3 的两种训练:LoRA 微调用 facade 图,ControlNet 用线稿配对。

## 合成器(synth.py)

复用现有 `SimulatorGenerator`(与网页生成同一条路),批量出图并写 metadata.jsonl。数据管线只当消费者,不修改生成器内部——网页出图功能零风险。

- 每次模拟器调用产出 `facade.png` + `floorplan.png`,重命名为 `synth_<id>.png` 存入数据集,`kind` 区分。
- **固定随机种子抽样参数**(风格/层数/宽深/材质/屋顶/场地),保证每次生成的数据集完全一样,训练可复现。
- 产出规模:4 风格 × 每风格 50 组参数 = 200 组,每组 2 张图 = 400 张 + metadata.jsonl。够验证管线、量又不大的小样本。
- 主函数 `generate_dataset(out_dir, per_style, seed)`。

## 公开数据下载器(download.py)

**本期不写代码**,只定产出契约:输出数据格式必须与合成数据一致(图片进 `images/`,每行 metadata.jsonl),差别只在 `source: "web"`、不带完整参数标签。实现留待网络验证后追加。不为未实现功能写空壳。

## 清洗器(clean.py)

对合成数据做最小清洗(合成数据天然干净,复杂清洗留给将来 web 分支):

1. **损坏图剔除**:PIL 打开校验,打不开则删除文件并移除索引行
2. **重复去重**:文件内容 sha256 哈希找重复,保留一张,其余删除并更新索引
3. **标签校验**:metadata.jsonl 每条 `params` 能被 `BuildingParams` 解析,失败行删除
4. **manifest 重写**:上述删除后重写 metadata.jsonl,保证索引与磁盘文件严格一致

主函数 `clean_dataset(dataset_dir)`。

## 校验器(validate.py)

只读检查,不修改数据,输出「通过/失败 + 问题清单」。训练脚本跑前必跑。

1. **目录结构**:`images/` 存在且非空,`metadata.jsonl` 存在
2. **索引-文件一致性**:每条记录的 `image` 路径在磁盘存在;磁盘每个文件在索引有记录(双向核对)
3. **标签合法性**:每条 `params` 解析为合法 `BuildingParams`
4. **图片可读性**:PIL 能打开、尺寸与记录一致
5. 全部通过 → `Dataset OK (N images)`;有失败 → 问题清单 + 非零退出码

主函数 `validate_dataset(dataset_dir) -> bool`。

## 实现结构与测试

### 包结构

```
data/
├── __init__.py
├── synth.py
├── clean.py
└── validate.py
```

独立于 `generation/`/`backend/` 的顶层包,将来 `download.py` 加同一层。

### 命令行入口

三个模块各配 `python -m data.synth / data.clean / data.validate`,argparse 参数(目录、风格数、种子等),不引入额外依赖。

### 测试(pytest)

- **synth**:小合成(2 风格 × 2 组),断言图片存在、jsonl 行数 = 图片数、字段完整、种子固定时两次输出一致
- **clean**:构造含坏图/重复图/坏标签的临时数据集,断言坏图被删、索引正确
- **validate**:干净数据集通过;删图/写坏标签 → 失败且报出问题
- 测试输出到 `tmp_path`,不污染真实数据

### Makefile 命令

```
make data-synth
make data-clean
make data-validate
```

## 本期交付清单

- `data/` 三个模块 + 测试全绿
- `data/datasets/synth_demo/` 小样本数据集(4 风格 × 50 组 = 400 张)生成并通过校验
- 设计文档 + 实施计划存档
- 公开下载器契约已写清,代码留待网络验证后追加

## 里程碑3 前置关系

- LoRA 微调:用 `kind=facade` 的合成图
- ControlNet:合成线稿天然作条件图,`kind` 字段筛选
- 真实数据(web)后续补充,提升效果图真实感
