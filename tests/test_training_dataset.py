import json
from pathlib import Path

from training.dataset import (
    build_samples,
    filter_by_style,
    load_facade_records,
    make_prompt,
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
            base = {
                "style": style,
                "floors": 2,
                "width_m": 10.0,
                "depth_m": 8.0,
                "materials": ["brick"],
                "roof": "flat",
                "environment": "suburb",
            }
            for kind in ("facade", "floorplan"):
                img = f"images/synth_{i}{j}_{kind}.png"
                im.save(ds / img)
                records.append(
                    {
                        "id": f"r{i}{j}_{kind}",
                        "image": img,
                        "source": "synth",
                        "kind": kind,
                        "params": base,
                        "width_px": 640,
                        "height_px": 480,
                    }
                )
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
    p = make_prompt(
        {
            "style": "modern",
            "floors": 2,
            "width_m": 10.0,
            "depth_m": 8.0,
            "materials": ["brick"],
            "roof": "flat",
            "environment": "suburb",
        }
    )
    assert "modern minimalist" in p
    assert "2-story" in p


def test_build_samples(tmp_path: Path):
    ds = _make_ds(tmp_path)
    samples = build_samples(ds, "nordic")
    assert len(samples) == 2
    for s in samples:
        assert s["image"].exists()
        assert "nordic" in s["prompt"]
