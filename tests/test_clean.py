import json
from pathlib import Path

from data.clean import clean_dataset
from data.synth import generate_dataset


def _write_bad_label(ds: Path) -> None:
    """把第一条记录 params 改成非法风格。"""
    path = ds / "metadata.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["params"]["style"] = "baroque"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_clean_removes_missing_file(tmp_path: Path):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    rows = [
        json.loads(line)
        for line in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    victim = ds / rows[0]["image"]
    victim.unlink()
    deleted_files, removed_records = clean_dataset(ds)
    assert deleted_files >= 1
    assert removed_records == 1
    after = (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(after) == len(rows) - 1


def test_clean_removes_bad_label(tmp_path: Path):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    _write_bad_label(ds)
    deleted_files, removed_records = clean_dataset(ds)
    assert removed_records == 1
    assert deleted_files >= 1  # 对应图片一并删除


def test_clean_idempotent_on_clean_data(tmp_path: Path):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=2, seed=3)
    before = (ds / "metadata.jsonl").read_text(encoding="utf-8")
    deleted_files, removed_records = clean_dataset(ds)
    assert (deleted_files, removed_records) == (0, 0)
    assert (ds / "metadata.jsonl").read_text(encoding="utf-8") == before


def test_clean_rewrites_index_consistent_with_disk(tmp_path: Path):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=2, seed=5)
    rows = [
        json.loads(line)
        for line in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (ds / rows[0]["image"]).unlink()
    clean_dataset(ds)
    after = [
        json.loads(line)
        for line in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    for r in after:
        assert (ds / r["image"]).exists()
