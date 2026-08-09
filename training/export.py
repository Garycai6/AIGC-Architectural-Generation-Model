"""产物导出——LoRA 权重文件命名与输出目录。纯逻辑,不 import torch。"""

from pathlib import Path


def lora_filename(style: str) -> str:
    return f"{style}.safetensors"


def lora_output_path(output_dir: Path, style: str) -> Path:
    return output_dir / lora_filename(style)


def ensure_output_dir(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
