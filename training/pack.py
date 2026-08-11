"""LoRA 产物打包——训练 .safetensors 转 Replicate 可用的 tar.gz。纯逻辑,不 import torch。"""

import io
import json
import tarfile
from pathlib import Path

from training.export import lora_output_path


def pack_lora(output_dir: Path, style: str, weight_scale: float = 1.0) -> Path:
    """把 {style}.safetensors 打成 {style}.tar(内含 lora.safetensors + special_params.json)。

    Replicate 的 LoRA 注入要求 tar 内权重重命名为 lora.safetensors;special_params.json
    记录 LoRA 权重缩放(社区惯例)。成员名扁平,无目录前缀。
    """
    src = lora_output_path(output_dir, style)
    if not src.exists():
        raise FileNotFoundError(f"LoRA 权重不存在: {src}")

    out = output_dir / f"{style}.tar"
    with open(src, "rb") as f, tarfile.open(out, "w:gz") as tar:
        data = f.read()
        info = tarfile.TarInfo(name="lora.safetensors")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

        special = json.dumps({"weight": weight_scale}, separators=(",", ":")).encode()
        info = tarfile.TarInfo(name="special_params.json")
        info.size = len(special)
        tar.addfile(info, io.BytesIO(special))
    return out
