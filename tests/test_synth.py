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
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))  # id 唯一


def test_generate_dataset_cross_style_unique(tmp_path: Path):
    """跨风格参数不得重复——修复采样器跨风格重复缺陷。"""
    import collections

    out = tmp_path / "ds"
    generate_dataset(out, per_style=50, seed=42)
    rows = [
        json.loads(line)
        for line in (out / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    by_style: dict[str, list[str]] = collections.defaultdict(list)
    for r in rows:
        by_style[r["params"]["style"]].append(r["params"])
    styles = list(by_style)
    assert len(styles) == 4
    for i in range(len(styles)):
        for j in range(i + 1, len(styles)):
            # 比较不含 style 字段的参数——修复跨风格抽样重复缺陷
            def _strip_style(p: dict) -> dict:
                d = dict(p)
                d.pop("style", None)
                return d

            si_params = [json.dumps(_strip_style(p), sort_keys=True) for p in by_style[styles[i]]]
            sj_params = [json.dumps(_strip_style(p), sort_keys=True) for p in by_style[styles[j]]]
            assert set(si_params) != set(sj_params), (
                f"styles {styles[i]} and {styles[j]} produce identical param sets"
            )


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
