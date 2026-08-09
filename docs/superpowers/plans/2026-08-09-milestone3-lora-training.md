# 里程碑3:SDXL LoRA 云端训练管线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `training/` 包,在云端 AutoDL 4090 上跑通 SDXL LoRA 训练,产出 4 个独立风格 LoRA(.safetensors)+ 样例图,为效果图细节错误根治铺路。

**Architecture:** `training/` 包按「纯逻辑本机可测 / diffusers 云端跑」分层:config/dataset/export 纯函数不 import torch,diffusers/torch 只出现在 train.py/verify.py(云端 `python -m training.train` 执行)。数据直读 `data/datasets/<name>/metadata.jsonl`(复用 data 包模式),不引入 datasets 依赖。

**Tech Stack:** Python 3.11 + argparse(CLI);云端 torch + diffusers + peft + accelerate(gpu 可选依赖组);Pillow。

## Global Constraints

- 本机 **无 torch/diffusers**,测试一律不 import 这两个库;涉及它们的代码用 mock/skip(参照 `tests/test_replicate_gen.py` 模式)
- 训练数据直读 `data/datasets/<name>/metadata.jsonl` + `images/`,不新增 datasets 依赖
- `training/` 已是 wheel 包(见 pyproject.toml hatch packages),`__init__.py` 必须存在
- ruff:`line-length=100`,规则 E/F/I/UP/B;`ruff check` 与 `ruff format` 双绿
- commit 风格:中文,前缀 `feat:`/`test:`/`docs:`(遵循仓库现有风格)
- 训练产物(weight 文件、样例图)不入库;`training/` 代码入库
- 训练配置 CLI 用 argparse;config 数据结构用 dataclass(不用 pydantic,保持轻)

---

### Task 1: training 包骨架 + config.py 训练配置

**Files:**
- Create: `training/__init__.py`
- Create: `training/config.py`
- Create: `tests/test_training_config.py`

**Interfaces:**
- Produces: `training.config.TrainConfig`(dataclass)、`training.config.build_config(args) -> TrainConfig`、`training.config.CLI_ARGS`(argparse 参数列表)

**TrainConfig 字段**(全部默认值,dataclass):
```python
@dataclass(frozen=True)
class TrainConfig:
    dataset_dir: Path          # data/datasets/<name>/,必填
    style: str                 # 风格,必填(modern/neoclassic/european/nordic)
    output_dir: Path           # 产物输出目录,默认 ./lora_out
    resolution: int = 1024     # 训练分辨率(方形)
    train_batch_size: int = 1
    learning_rate: float = 1e-4
    epochs: int = 50           # 数据循环轮数(数据小,靠 epochs 凑步数)
    seed: int = 42
```

- [ ] **Step 1: 写失败测试**

创建 `tests/test_training_config.py`:

```python
import argparse
from pathlib import Path

from training.config import build_config


def test_build_config_defaults():
    cfg = build_config(argparse.Namespace(
        dataset_dir="data/datasets/synth_demo", style="modern",
        output_dir=None,
    ))
    assert cfg.dataset_dir == Path("data/datasets/synth_demo")
    assert cfg.style == "modern"
    assert cfg.output_dir == Path("lora_out")
    assert cfg.resolution == 1024
    assert cfg.train_batch_size == 1
    assert cfg.learning_rate == 1e-4
    assert cfg.epochs == 50
    assert cfg.seed == 42


def test_build_config_overrides():
    cfg = build_config(argparse.Namespace(
        dataset_dir="ds", style="nordic", output_dir="out",
        resolution=512, train_batch_size=2, learning_rate=5e-5,
        epochs=10, seed=7,
    ))
    assert cfg.output_dir == Path("out")
    assert cfg.resolution == 512
    assert cfg.train_batch_size == 2
    assert cfg.learning_rate == 5e-5
    assert cfg.epochs == 10
    assert cfg.seed == 7


def test_cli_args_include_all_fields():
    import argparse
    from training.config import CLI_ARGS
    parser = argparse.ArgumentParser()
    for names, kwargs in CLI_ARGS:
        parser.add_argument(*names, **kwargs)
    ns = parser.parse_args([
        "--dataset-dir", "ds", "--style", "modern",
        "--output-dir", "out", "--resolution", "512",
        "--train-batch-size", "2", "--learning-rate", "5e-5",
        "--epochs", "10", "--seed", "7",
    ])
    assert ns.dataset_dir == "ds"
    assert ns.style == "modern"
    assert ns.output_dir == "out"
    assert ns.resolution == 512
    assert ns.epochs == 10
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_training_config.py -v`
Expected: FAIL(ModuleNotFoundError: No module named 'training')

- [ ] **Step 3: 实现 training/config.py**

```python
"""训练配置——CLI 参数解析 + 不可变配置对象。纯逻辑,不 import torch。"""

from dataclasses import dataclass, field
from pathlib import Path

# (argparse 位置/可选参数名, 关键字参数字典) 列表
CLI_ARGS: list[tuple[tuple[str, ...], dict]] = [
    (("--dataset-dir",), {"type": Path, "required": True,
                          "help": "数据集目录 data/datasets/<name>/"}),
    (("--style",), {"required": True, "choices": ["modern", "neoclassic",
                   "european", "nordic"], "help": "要训练的风格"}),
    (("--output-dir",), {"type": Path, "default": None,
                         "help": "产物输出目录,默认 ./lora_out"}),
    (("--resolution",), {"type": int, "default": 1024}),
    (("--train-batch-size",), {"type": int, "default": 1}),
    (("--learning-rate",), {"type": float, "default": 1e-4}),
    (("--epochs",), {"type": int, "default": 50}),
    (("--seed",), {"type": int, "default": 42}),
]


@dataclass(frozen=True)
class TrainConfig:
    dataset_dir: Path
    style: str
    output_dir: Path = field(default_factory=lambda: Path("lora_out"))
    resolution: int = 1024
    train_batch_size: int = 1
    learning_rate: float = 1e-4
    epochs: int = 50
    seed: int = 42


def build_config(args) -> TrainConfig:
    """从 argparse Namespace 构建 TrainConfig。"""
    return TrainConfig(
        dataset_dir=Path(args.dataset_dir),
        style=args.style,
        output_dir=Path(args.output_dir) if args.output_dir else Path("lora_out"),
        resolution=args.resolution,
        train_batch_size=args.train_batch_size,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        seed=args.seed,
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_training_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add training/__init__.py training/config.py tests/test_training_config.py
git commit -m "feat: training 包骨架 + 训练配置 config"
```

---

### Task 2: dataset.py 训练样本构建

**Files:**
- Create: `training/dataset.py`
- Create: `tests/test_training_dataset.py`

**Interfaces:**
- Consumes: `training.config.TrainConfig`(Task 1);`generation.params.model.BuildingParams`(已存在);`generation.generators.api.prompt.build_prompt`(已存在)
- Produces:
  - `training.dataset.load_facade_records(dataset_dir: Path) -> list[dict]` — 从 metadata.jsonl 读所有 `kind == "facade"` 记录
  - `training.dataset.filter_by_style(records, style: str) -> list[dict]` — 按 `params.style` 过滤
  - `training.dataset.make_prompt(params_dict: dict, lang: str = "en") -> str` — 用 `build_prompt` 构造 facade prompt
  - `training.dataset.build_samples(dataset_dir: Path, style: str, resolution: int) -> list[dict]` — 返回 `[{"image": Path, "prompt": str}]`,处理图片缩放

**核心逻辑:**
- 从 metadata.jsonl 读记录(复用 data 包 jsonl 读取方式)
- 过滤 `kind == "facade"`,再按 `style` 过滤
- 每条记录构造 prompt:`build_prompt(BuildingParams(**r["params"]), "facade", "en")`
- 图片路径:相对 metadata.jsonl 所在目录
- 缩放逻辑:`build_samples` 返回样本时图片仍是原图路径,缩放放云端训练循环(torch 处理后做)——**本任务只验证记录读取/过滤/prompt,不碰图片像素**

- [ ] **Step 1: 写失败测试**

创建 `tests/test_training_dataset.py`:

```python
import json
from pathlib import Path

from training.dataset import (
    build_samples, filter_by_style, load_facade_records, make_prompt,
)


def _make_ds(tmp_path: Path) -> Path:
    """构造含 2 风格 × 2 组 facade + floorplan 的小数据集。"""
    ds = tmp_path / "ds"
    (ds / "images").mkdir(parents=True)
    from PIL import Image
    im = Image.new("RGB", (640, 480), (200, 100, 50))
    records = []
    for i, style in enumerate(["modern", "nordic"]):
        for j in range(2):
            base = {"style": style, "floors": 2, "width_m": 10.0,
                    "depth_m": 8.0, "materials": ["brick"], "roof": "flat",
                    "environment": "suburb"}
            for kind in ("facade", "floorplan"):
                img = f"images/synth_{i}{j}_{kind}.png"
                im.save(ds / img)
                records.append({
                    "id": f"r{i}{j}_{kind}", "image": img, "source": "synth",
                    "kind": kind, "params": base, "width_px": 640,
                    "height_px": 480,
                })
    with (ds / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return ds


def test_load_facade_records_filters_kind(tmp_path: Path):
    ds = _make_ds(tmp_path)
    facades = load_facade_records(ds)
    assert len(facades) == 4  # 2 风格 × 2 组 facade
    assert all(r["kind"] == "facade" for r in facades)


def test_filter_by_style(tmp_path: Path):
    ds = _make_ds(tmp_path)
    facades = load_facade_records(ds)
    modern = filter_by_style(facades, "modern")
    assert len(modern) == 2
    assert all(r["params"]["style"] == "modern" for r in modern)


def test_make_prompt_includes_style():
    p = make_prompt({"style": "modern", "floors": 2, "width_m": 10.0,
                     "depth_m": 8.0, "materials": ["brick"], "roof": "flat",
                     "environment": "suburb"})
    assert "modern minimalist" in p
    assert "2-story" in p


def test_build_samples(tmp_path: Path):
    ds = _make_ds(tmp_path)
    samples = build_samples(ds, "nordic")
    assert len(samples) == 2
    for s in samples:
        assert s["image"].exists()
        assert "nordic" in s["prompt"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_training_dataset.py -v`
Expected: FAIL(ModuleNotFoundError: No module named 'training.dataset')

- [ ] **Step 3: 实现 training/dataset.py**

```python
"""训练样本构建——从数据集读 facade 记录,按风格过滤,构造 prompt。

纯逻辑,不 import torch/diffusers。图片缩放放云端训练循环。
"""

import json
from pathlib import Path

from generation.generators.api.prompt import build_prompt
from generation.params.model import BuildingParams


def load_facade_records(dataset_dir: Path) -> list[dict]:
    """读 metadata.jsonl,返回 kind == 'facade' 的记录列表。"""
    records = []
    metadata = dataset_dir / "metadata.jsonl"
    with metadata.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["kind"] == "facade":
                records.append(r)
    return records


def filter_by_style(records: list[dict], style: str) -> list[dict]:
    return [r for r in records if r["params"]["style"] == style]


def make_prompt(params_dict: dict, lang: str = "en") -> str:
    """用现有 prompt 构建器构造 facade prompt。"""
    params = BuildingParams(**params_dict)
    return build_prompt(params, "facade", lang)


def build_samples(dataset_dir: Path, style: str, resolution: int = 1024) -> list[dict]:
    """返回 [{'image': Path, 'prompt': str}]。图片为原图路径,缩放云端做。"""
    records = load_facade_records(dataset_dir)
    styled = filter_by_style(records, style)
    return [
        {
            "image": dataset_dir / r["image"],
            "prompt": make_prompt(r["params"]),
        }
        for r in styled
    ]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_training_dataset.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add training/dataset.py tests/test_training_dataset.py
git commit -m "feat: 训练样本构建 dataset(读 facade 记录/按风格过滤/构造 prompt)"
```

---

### Task 3: export.py 产物导出

**Files:**
- Create: `training/export.py`
- Create: `tests/test_training_export.py`

**Interfaces:**
- Produces:
  - `training.export.lora_filename(style: str) -> str` — 返回 `f"{style}.safetensors"`
  - `training.export.lora_output_path(output_dir: Path, style: str) -> Path` — `output_dir / lora_filename(style)`
  - `training.export.ensure_output_dir(output_dir: Path) -> Path` — mkdir,返回 output_dir

- [ ] **Step 1: 写失败测试**

创建 `tests/test_training_export.py`:

```python
from pathlib import Path

from training.export import ensure_output_dir, lora_filename, lora_output_path


def test_lora_filename():
    assert lora_filename("modern") == "modern.safetensors"
    assert lora_filename("neoclassic") == "neoclassic.safetensors"


def test_lora_output_path():
    p = lora_output_path(Path("out"), "nordic")
    assert p == Path("out") / "nordic.safetensors"


def test_ensure_output_dir_creates(tmp_path: Path):
    out = ensure_output_dir(tmp_path / "nested" / "out")
    assert out.is_dir()


def test_ensure_output_dir_idempotent(tmp_path: Path):
    out = ensure_output_dir(tmp_path / "out")
    assert ensure_output_dir(tmp_path / "out") == out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_training_export.py -v`
Expected: FAIL(ModuleNotFoundError: No module named 'training.export')

- [ ] **Step 3: 实现 training/export.py**

```python
"""产物导出——LoRA 权重文件命名与输出目录。纯逻辑,不 import torch。"""

from pathlib import Path


def lora_filename(style: str) -> str:
    return f"{style}.safetensors"


def lora_output_path(output_dir: Path, style: str) -> Path:
    return output_dir / lora_filename(style)


def ensure_output_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_training_export.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add training/export.py tests/test_training_export.py
git commit -m "feat: 产物导出 export(LoRA 文件名/输出目录)"
```

---

### Task 4: train.py 训练入口 + verify.py 验证入口

**Files:**
- Create: `training/train.py`
- Create: `training/verify.py`
- Create: `tests/test_training_skip.py`

**Interfaces:**
- Consumes: `training.config.build_config`、`TrainConfig`(Task 1);`training.dataset.build_samples`(Task 2);`training.export.lora_output_path`、`ensure_output_dir`(Task 3)
- Produces: `training.train.main(argv: list[str]) -> int`(CLI 入口,云端跑);`training.verify.main(argv: list[str]) -> int`

**关键设计:**
- `train.py`/`verify.py` 含 diffusers/torch 代码,**本机不 import**(guarded import + pytest skip)
- `main(argv)` 接收参数列表,先 build_config → build_samples → 再构造云端 pipeline(仅在 torch 可用时)
- `main` 对参数解析/数据加载这些「无 torch」部分本机可测;torch 部分 mock

- [ ] **Step 1: 写失败测试**

创建 `tests/test_training_skip.py`:

```python
"""train/verify 含 diffusers/torch,本机无 GPU 直接 skip(与 replicate 测试同思路)。"""

import pytest

torch = pytest.importorskip("torch")


def test_torch_available_in_ci():
    assert torch is not None
```

- [ ] **Step 2: 跑测试确认**

Run: `uv run pytest tests/test_training_skip.py -v`
Expected: SKIPPED(本机无 torch,`pytest.importorskip` 自动跳过)

- [ ] **Step 3: 实现 training/train.py**

```python
"""SDXL LoRA 训练入口——云端 AutoDL 执行。

本机不 import torch/diffusers:torch 代码在运行时 guarded import 内,本机只测
参数解析与数据准备部分(不进入训练循环)。
"""

import sys

from training.config import CLI_ARGS, build_config
from training.dataset import build_samples
from training.export import ensure_output_dir, lora_output_path


def _parse_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="training.train")
    for names, kwargs in CLI_ARGS:
        parser.add_argument(*names, **kwargs)
    return parser.parse_args(argv)


def _train_loop(cfg):
    """SDXL LoRA 训练循环——仅云端(torch 可用)执行。

    标准 diffusers LoRA 训练:加载 SDXL base,加 peft LoRA,用风格图做
    目标,输出 .safetensors。本机无 torch 不可达,测试 mock 掉。训练循环
    的正确性以云端跑通为准(本机无法验证 torch 行为)。
    """
    import torch
    from diffusers import AutoencoderKL, StableDiffusionXLPipeline
    from diffusers.optimization import get_scheduler
    from diffusers.utils import convert_state_dict_to_diffusers
    from peft import LoraConfig, get_peft_model
    from safetensors.torch import save_file
    from transformers import AutoTokenizer
    from PIL import Image

    # 1. 加载 SDXL base(仅训练,省显存:不加载 VAE decode)
    vae = AutoencoderKL.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", subfolder="vae"
    )
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        vae=vae, torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True,
    )
    pipe.to("cuda")
    pipe.vae.to(torch.float32)  # fp16 VAE 训练不稳定,回 float32

    tokenizer = AutoTokenizer.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", subfolder="tokenizer"
    )
    text_encoder = pipe.text_encoder
    text_encoder_2 = pipe.text_encoder_2
    unet = pipe.unet
    unet.enable_gradient_checkpointing()

    # 2. 加 peft LoRA(unet)
    lora_config = LoraConfig(
        r=16, lora_alpha=32, target_modules=[
            "to_q", "to_k", "to_v", "to_out.0",
            "ff.net.0.proj", "ff.net.2",
        ],
        lora_dropout=0.0, bias="none",
    )
    unet = get_peft_model(unet, lora_config)

    # 3. 数据(每张图一个样本,prompt 用 build_prompt 构造)
    samples = build_samples(cfg.dataset_dir, cfg.style, cfg.resolution)
    images = [Image.open(s["image"]).convert("RGB") for s in samples]
    prompts = [s["prompt"] for s in samples]

    # 4. 优化器 + 调度器
    optimizer = torch.optim.AdamW(unet.parameters(), lr=cfg.learning_rate)
    steps = len(images) * cfg.epochs
    lr_scheduler = get_scheduler(
        "constant", optimizer=optimizer, num_warmup_steps=0,
        num_training_steps=steps,
    )

    # 5. 训练循环(逐张样本训练,epochs 次)
    unet.train()
    noise_scheduler = pipe.scheduler
    for epoch in range(cfg.epochs):
        for img, prompt in zip(images, prompts):
            pixel_values = torch.tensor(
                [img.resize((cfg.resolution, cfg.resolution))],
                dtype=torch.float32,
            ).permute(0, 3, 1, 2) / 127.5 - 1.0
            pixel_values = pixel_values.to(device="cuda", dtype=torch.float16)

            # 双 text encoder 编码 prompt
            text_inputs = tokenizer(
                prompt, padding="max_length", max_length=77, truncation=True,
                return_tensors="pt",
            )
            encoder_hidden_states = text_encoder(
                text_inputs.input_ids.to("cuda")
            )[0]
            text_inputs_2 = tokenizer(
                prompt, padding="max_length", max_length=77, truncation=True,
                return_tensors="pt",
            )
            encoder_hidden_states_2 = text_encoder_2(
                text_inputs_2.input_ids.to("cuda")
            )[0]

            # 加噪声 + denoising objective
            noise = torch.randn_like(pixel_values)
            timesteps = torch.randint(
                0, noise_scheduler.config.num_train_timesteps,
                (1,), device="cuda",
            ).long()
            noisy = noise_scheduler.add_noise(pixel_values, noise, timesteps)
            noise_pred = unet(
                noisy, timesteps,
                encoder_hidden_states=encoder_hidden_states,
                added_cond_kwargs={
                    "text_embeds": encoder_hidden_states_2,
                    "time_ids": torch.tensor(
                        [[cfg.resolution, cfg.resolution, 0, 0,
                          cfg.resolution, cfg.resolution]],
                        device="cuda",
                    ),
                },
            ).sample

            loss = torch.nn.functional.mse_loss(
                noise_pred.float(), noise.float(), reduction="mean"
            )
            loss.backward()
            optimizer.step()
            lr_scheduler.step()
            optimizer.zero_grad()

    # 6. 保存 LoRA .safetensors
    lora_path = lora_output_path(cfg.output_dir, cfg.style)
    unet_state = convert_state_dict_to_diffusers(unet.get_peft_state_dict())
    save_file(unet_state, lora_path)
    print(f"[training] 已保存 LoRA → {lora_path}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    cfg = build_config(args)
    ensure_output_dir(cfg.output_dir)
    samples = build_samples(cfg.dataset_dir, cfg.style, cfg.resolution)
    if not samples:
        print(f"错误:风格 {cfg.style} 无 facade 数据")
        return 1
    print(f"[training] {cfg.style}: {len(samples)} 张 facade 图")
    print(f"[training] 输出: {lora_output_path(cfg.output_dir, cfg.style)}")
    _train_loop(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 写测试(mock 掉 _train_loop)**

创建 `tests/test_training_train.py`:

```python
from pathlib import Path
from unittest.mock import patch

from training.train import main


def test_main_reports_no_data(tmp_path: Path, capsys):
    # 空数据集目录 -> 返回 1
    ds = tmp_path / "ds"
    ds.mkdir()
    (ds / "metadata.jsonl").write_text("", encoding="utf-8")
    rc = main(["--dataset-dir", str(ds), "--style", "modern",
               "--output-dir", str(tmp_path / "out")])
    assert rc == 1
    assert "无 facade 数据" in capsys.readouterr().out


def test_main_calls_train_loop(tmp_path: Path):
    # 构造含 modern facade 的最小数据集
    import json
    from PIL import Image
    ds = tmp_path / "ds"
    (ds / "images").mkdir(parents=True)
    Image.new("RGB", (64, 64), (0, 0, 0)).save(ds / "images" / "f.png")
    records = [{
        "id": "r1", "image": "images/f.png", "source": "synth",
        "kind": "facade", "width_px": 64, "height_px": 64,
        "params": {"style": "modern", "floors": 2, "width_m": 10.0,
                   "depth_m": 8.0, "materials": ["brick"], "roof": "flat",
                   "environment": "suburb"},
    }]
    with (ds / "metadata.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps(records[0]) + "\n")
    with patch("training.train._train_loop") as mock_loop:
        rc = main(["--dataset-dir", str(ds), "--style", "modern",
                   "--output-dir", str(tmp_path / "out")])
    assert rc == 0
    mock_loop.assert_called_once()
    assert (tmp_path / "out").is_dir()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/test_training_train.py -v`
Expected: 2 passed

- [ ] **Step 6: 实现 training/verify.py**

```python
"""验证入口——加载训好的 LoRA 出样例图(云端执行)。

本机无 torch,diffusers 代码仅在云端运行;main 的参数解析部分本机可测。
"""

import sys

from training.config import CLI_ARGS, build_config
from training.dataset import make_prompt
from training.export import lora_output_path


def _parse_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="training.verify")
    for names, kwargs in CLI_ARGS:
        parser.add_argument(*names, **kwargs)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    cfg = build_config(args)
    lora_path = lora_output_path(cfg.output_dir, cfg.style)
    if not lora_path.exists():
        print(f"错误:LoRA 不存在 {lora_path}")
        return 1

    # 云端采样:加载 base SDXL + LoRA,出样例图
    import torch
    from diffusers import StableDiffusionXLPipeline

    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16, variant="fp16", use_safetensors=True,
    )
    pipe.to("cuda")
    pipe.load_lora_weights(str(lora_path))

    prompt = make_prompt(
        {"style": cfg.style, "floors": 2, "width_m": 10.0, "depth_m": 8.0,
         "materials": ["brick"], "roof": "flat", "environment": "suburb"}
    )
    out = cfg.output_dir / f"{cfg.style}_sample.png"
    image = pipe(
        prompt=prompt, num_inference_steps=30, guidance_scale=7.5,
        height=1024, width=1024,
    ).images[0]
    image.save(out)
    print(f"[verify] 样例图 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: 跑测试确认(train 全绿 + skip)**

Run: `uv run pytest tests/test_training_train.py tests/test_training_skip.py -v`
Expected: 2 passed + 1 skipped

- [ ] **Step 8: Commit**

```bash
git add training/train.py training/verify.py tests/test_training_train.py tests/test_training_skip.py
git commit -m "feat: 训练/验证 CLI 入口 train/verify(配置/数据/产物骨架可测)"
```

---

### Task 5: __main__.py CLI 接线 + Makefile

**Files:**
- Create: `training/__main__.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `training.train.main`、`training.verify.main`(Task 4)
- Produces: `python -m training.train --dataset-dir ... --style ...` 可直接运行

- [ ] **Step 1: 写 __main__.py**

创建 `training/__main__.py`:

```python
"""python -m training 分派到 train / verify。"""

import sys


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("train", "verify"):
        print(__doc__)
        return 1
    sub, rest = sys.argv[1], sys.argv[2:]
    if sub == "train":
        from training.train import main as train_main
        return train_main(rest)
    from training.verify import main as verify_main
    return verify_main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 跑测试确认可调用**

Run: `uv run python -m training --help`
Expected: 打印 usage 并返回 0

- [ ] **Step 3: Makefile 加训练命令**

在 `.PHONY` 加 `train-lora`,末尾追加:

```make
train-lora:
	uv run python -m training train --dataset-dir data/datasets/synth_demo --style modern --output-dir lora_out
```

- [ ] **Step 4: 全量回归**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: 全部通过(原 69 + 新增 ~13 = 82 passed,含 1 skipped),ruff 双绿

- [ ] **Step 5: Commit**

```bash
git add training/__main__.py Makefile
git commit -m "feat: training CLI 接线 __main__ + Makefile 训练命令"
```

---

### Task 6: 交付文档 + 验证记录

**Files:**
- Create: `docs/superpowers/plans/2026-08-09-milestone3-lora-training.md`(本计划存档)
- Modify: `docs/gallery/smoke-test.md` 追加小节

**Interfaces:**
- Consumes: 全 tasks 成果

- [ ] **Step 1: 存档实施计划**

将本文件复制到 `docs/superpowers/plans/2026-08-09-milestone3-lora-training.md`。

- [ ] **Step 2: 记录验证结果**

在 `docs/gallery/smoke-test.md` 追加小节,记录:training 包 6 模块、测试数、ruff 绿、云端执行命令。

- [ ] **Step 3: 全量最终回归**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: 全部通过,ruff 双绿

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-08-09-milestone3-lora-training.md docs/gallery/smoke-test.md
git commit -m "docs: 里程碑3 LoRA 训练管线实施计划 + 验证记录"
```

---

## Self-Review 记录

- **Spec 覆盖**:config(Task 1)、dataset(Task 2)、export(Task 3)、train/verify(Task 4)、CLI 接线(Task 5)、交付(Task 6)。云端训练循环(_train_loop)已写完整 diffusers 实现,`verify` 已写 SDXL + LoRA 采样。
- **对 spec 的修正**:不引入 `datasets` 依赖——数据直读 metadata.jsonl(复用 data 包模式),更轻、本机可测。已在 Global Constraints 注明。
- **类型一致性**:`TrainConfig` 字段、`build_config`、`build_samples`、`lora_output_path` 在全部任务中一致。
- **不 import torch**:测试全部用纯逻辑 + mock(参照 replicate 测试模式);train/verify 的 torch 代码 guarded import,本机永不执行;`test_training_skip.py` 用 `pytest.importorskip("torch")` 自动跳过。
- **产物格式**:训练循环用 `safetensors.torch.save_file` 保存(非 torch.save pickle),`load_lora_weights` 才能读取。
