"""清洗器——坏图/重复/坏标签剔除,重写索引保证与磁盘一致。"""

import hashlib
import json
from pathlib import Path

from PIL import Image

from generation.params.model import BuildingParams


def _load_records(metadata: Path) -> list[dict]:
    with metadata.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_records(metadata: Path, records: list[dict]) -> None:
    with metadata.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_dataset(dataset_dir: Path) -> tuple[int, int]:
    """就地清洗。返回 (删除文件数, 移除记录数)。"""
    metadata = dataset_dir / "metadata.jsonl"
    records = _load_records(metadata)
    deleted_files = 0
    removed_records = 0

    def drop(r: dict) -> None:
        nonlocal deleted_files, removed_records
        removed_records += 1
        img = dataset_dir / r["image"]
        if img.exists():
            img.unlink()
        deleted_files += 1

    # 1. 文件存在 + 图片可读
    ok = []
    for r in records:
        img = dataset_dir / r["image"]
        try:
            with Image.open(img) as im:
                im.verify()
            ok.append(r)
        except Exception:
            drop(r)

    # 2. 内容去重
    seen: set[str] = set()
    dedup = []
    for r in ok:
        h = _file_hash(dataset_dir / r["image"])
        if h in seen:
            drop(r)
        else:
            seen.add(h)
            dedup.append(r)

    # 3. 标签校验
    final = []
    for r in dedup:
        try:
            BuildingParams(**r["params"])
            final.append(r)
        except Exception:
            drop(r)

    _write_records(metadata, final)
    return deleted_files, removed_records


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="清洗数据集")
    parser.add_argument("--dir", type=Path, required=True, help="数据集目录")
    args = parser.parse_args()
    deleted_files, removed_records = clean_dataset(args.dir)
    print(f"删除 {deleted_files} 个文件,移除 {removed_records} 条记录")
