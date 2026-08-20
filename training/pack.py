"""LoRA 产物打包——训练 .safetensors 转 Replicate 可用的 tar.gz。纯逻辑,不 import torch。"""

import io
import json
import tarfile
from pathlib import Path

from training.export import lora_output_path


def pack_lora(output_dir: Path, style: str, weight_scale: float = 1.0) -> Path:
    """把 {style}.safetensors 打成 {style}.tar(内含 lora.safetensors
    + special_params.json + embeddings.pti)。

    Replicate 的 LoRA 注入要求 tar 内权重重命名为 lora.safetensors;special_params.json
    记录 LoRA 权重缩放(社区惯例);embeddings.pti 是文本反演占位(fermat/cog-sdxl 无条件
    读取该文件,缺失会报 No such file,故打包空占位)。成员名扁平,无目录前缀。
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

        # 文本反演占位(空),供 load_embeddings 读取
        info = tarfile.TarInfo(name="embeddings.pti")
        info.size = 0
        tar.addfile(info, io.BytesIO(b""))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="training.pack")
    parser.add_argument("--output-dir", required=True, help="含训练产物的目录")
    parser.add_argument("--style", required=True, help="风格名(modern/neoclassic/european/nordic)")
    parser.add_argument("--weight", type=float, default=1.0, help="LoRA 权重缩放(默认 1.0)")
    args = parser.parse_args(argv)

    path = pack_lora(Path(args.output_dir), args.style, args.weight)
    print(f"[pack] 已打包 → {path}")
    return 0
