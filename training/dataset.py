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
    """用现有 prompt 构建器构造 facade prompt(统一小写)。"""
    params = BuildingParams(**params_dict)
    return build_prompt(params, "facade", lang).lower()


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
