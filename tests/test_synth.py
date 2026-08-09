import json
from pathlib import Path

from data.synth import _sample_params, generate_dataset
from generation.params.model import STYLE_NAMES, BuildingParams


def test_sample_params_valid(tmp_path: Path):
    import random

    rng = random.Random(0)
    for style in STYLE_NAMES:
        p = _sample_params(rng, style)
        assert isinstance(p, BuildingParams)
        assert p.style == style


def test_generate_dataset_counts(tmp_path: Path):
    out = tmp_path / "ds"
    n = generate_dataset(out, per_style=2, seed=1)
    # 4 风格 × 2 组 × 2 种图(facade+floorplan)
    assert n == 4 * 2 * 2
    assert (out / "metadata.jsonl").exists()
    assert len(list((out / "images").glob("*.png"))) == n


def test_generate_dataset_metadata_schema(tmp_path: Path):
    out = tmp_path / "ds"
    generate_dataset(out, per_style=1, seed=2)
    with (out / "metadata.jsonl").open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    for r in rows:
        assert set(r) == {
            "id",
            "image",
            "source",
            "kind",
            "params",
            "width_px",
            "height_px",
        }
        assert r["source"] == "synth"
        assert r["kind"] in ("facade", "floorplan")
        assert (out / r["image"]).exists()
        BuildingParams(**r["params"])


def test_generate_dataset_deterministic(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    generate_dataset(a, per_style=2, seed=7)
    generate_dataset(b, per_style=2, seed=7)
    assert (a / "metadata.jsonl").read_bytes() == (b / "metadata.jsonl").read_bytes()
    fa = sorted(p.name for p in (a / "images").glob("*.png"))
    fb = sorted(p.name for p in (b / "images").glob("*.png"))
    assert fa == fb
    for name in fa:
        assert (a / "images" / name).read_bytes() == (b / "images" / name).read_bytes()
