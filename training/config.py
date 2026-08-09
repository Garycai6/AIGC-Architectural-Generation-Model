"""训练配置——CLI 参数解析 + 不可变配置对象。纯逻辑,不 import torch。"""

from dataclasses import dataclass, field
from pathlib import Path

# (argparse 位置/可选参数名, 关键字参数字典) 列表
CLI_ARGS: list[tuple[tuple[str, ...], dict]] = [
    (
        ("--dataset-dir",),
        {"type": str, "required": True, "help": "数据集目录 data/datasets/<name>/"},
    ),
    (
        ("--style",),
        {
            "required": True,
            "choices": ["modern", "neoclassic", "european", "nordic"],
            "help": "要训练的风格",
        },
    ),
    (("--output-dir",), {"type": str, "default": None, "help": "产物输出目录,默认 ./lora_out"}),
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
        resolution=getattr(args, "resolution", 1024),
        train_batch_size=getattr(args, "train_batch_size", 1),
        learning_rate=getattr(args, "learning_rate", 1e-4),
        epochs=getattr(args, "epochs", 50),
        seed=getattr(args, "seed", 42),
    )
