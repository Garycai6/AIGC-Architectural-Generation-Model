"""LoRA 键名转换:peft 格式 → diffusers LoRAAttnProcessor2_0 格式。

Replicate 的 sdxl-controlnet-lora(cog-sdxl 系)加载 LoRA 时,期望的键名是
diffusers 原生 LoRAAttnProcessor2_0 格式(`attn1.processor.to_q_lora.down.weight`),
而我们训练(peft)产出的是 `attn1.to_q.lora.down.weight`。此脚本做键名转换,
权重数据不变,无需重训。

用法: python -m training convert_lora_keys --input <src.safetensors> --output <dst.safetensors>
"""

import argparse
import json
import re
from pathlib import Path

# peft 键: base_model.model.down_blocks.1.attentions.0.transformer_blocks.0.attn1.to_q.lora.down.weight
# diffusers 键: down_blocks.1.attentions.0.transformer_blocks.0.attn1.processor.to_q_lora.down.weight
_KEY_RE = re.compile(
    r"^base_model\.model\.(?P<mod>.+?)\.attentions\.(?P<blk>\d+)\.transformer_blocks\.(?P<tb>\d+)\.(?P<attn>attn[12])\.(?P<proj>to_q|to_k|to_v|to_out\.0)\.lora\.(?P<du>down|up)\.weight$"
)


def convert_key(k: str) -> str | None:
    """转换单个键名;非 attention LoRA 键返回 None(应被过滤)。"""
    m = _KEY_RE.match(k)
    if not m:
        return None
    proj = m.group("proj")
    proj_diff = "to_out" if proj == "to_out.0" else proj
    return (
        f"{m.group('mod')}.attentions.{m.group('blk')}.transformer_blocks."
        f"{m.group('tb')}.{m.group('attn')}.processor.{proj_diff}_lora."
        f"{m.group('du')}.weight"
    )


def convert_safetensors(src: Path, dst: Path) -> None:
    """读 safetensors,转换键名,重写新文件。不 import torch。"""
    from safetensors import safe_open
    from safetensors.torch import save_file

    tensors = {}
    with safe_open(str(src), framework="pt", device="cpu") as f:
        for k in f.keys():
            new_k = convert_key(k)
            if new_k is None:
                print(f"跳过非 LoRA 键: {k}")
                continue
            tensors[new_k] = f.get_tensor(k)
    save_file(tensors, str(dst))
    print(f"已转换: {len(tensors)} 个键 → {dst}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="training.convert_lora_keys")
    parser.add_argument("--input", required=True, help="源 safetensors(peft 格式)")
    parser.add_argument("--output", required=True, help="输出 safetensors(diffusers 格式)")
    args = parser.parse_args(argv)
    convert_safetensors(Path(args.input), Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
