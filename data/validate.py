"""校验器——只读检查数据集,不修改数据。训练脚本跑前必跑。"""

import json
from pathlib import Path

from PIL import Image

from generation.params.model import BuildingParams


def _load_records(metadata: Path) -> list[dict]:
    with metadata.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def validate_dataset(dataset_dir: Path) -> bool:
    problems: list[str] = []
    images_dir = dataset_dir / "images"
    metadata = dataset_dir / "metadata.jsonl"

    if not images_dir.is_dir():
        problems.append("missing images/ directory")
    if not metadata.exists():
        problems.append("missing metadata.jsonl")

    if metadata.exists():
        records = _load_records(metadata)
        if not records:
            problems.append("metadata.jsonl is empty")
        # 索引 → 磁盘
        indexed = set()
        for r in records:
            img = dataset_dir / r["image"]
            if not img.exists():
                problems.append(f"missing {r['image']}")
                continue  # 不存在则跳过后面的 PIL 读取
            indexed.add(Path(r["image"]).name)
            # 标签合法性
            try:
                BuildingParams(**r["params"])
            except Exception as e:
                problems.append(f"bad params {r['id']}: {e}")
            # 图片可读性 + 尺寸
            try:
                with Image.open(img) as im:
                    if im.size != (r["width_px"], r["height_px"]):
                        problems.append(
                            f"size mismatch {r['image']}: "
                            f"record {r['width_px']}x{r['height_px']} "
                            f"actual {im.size[0]}x{im.size[1]}"
                        )
            except Exception as e:
                problems.append(f"unreadable {r['image']}: {e}")
        # 磁盘 → 索引(孤儿文件)
        if images_dir.is_dir():
            disk_files = {p.name for p in images_dir.iterdir() if p.is_file()}
            for name in sorted(disk_files - indexed):
                problems.append(f"orphan {name}")

    for p in problems:
        print(p)
    if not problems:
        print(f"Dataset OK ({len(records)} images)")
        return True
    return False


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="校验数据集")
    parser.add_argument("--dir", type=Path, required=True, help="数据集目录")
    args = parser.parse_args()
    sys.exit(0 if validate_dataset(args.dir) else 1)
