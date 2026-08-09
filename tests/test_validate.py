import json
from pathlib import Path

from data.synth import generate_dataset
from data.validate import validate_dataset


def test_validate_passes_on_clean(tmp_path: Path, capsys):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    assert validate_dataset(ds) is True
    captured = capsys.readouterr()
    assert "Dataset OK" in captured.out


def test_validate_fails_on_missing_file(tmp_path: Path, capsys):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    rows = [
        json.loads(line)
        for line in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    (ds / rows[0]["image"]).unlink()
    assert validate_dataset(ds) is False
    captured = capsys.readouterr()
    assert "missing" in captured.out


def test_validate_fails_on_orphan_file(tmp_path: Path, capsys):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    (ds / "images" / "orphan.png").write_bytes(b"not an image")
    assert validate_dataset(ds) is False
    captured = capsys.readouterr()
    assert "orphan" in captured.out


def test_validate_fails_on_bad_label(tmp_path: Path, capsys):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    rows = [
        json.loads(line)
        for line in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["params"]["style"] = "baroque"
    (ds / "metadata.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    assert validate_dataset(ds) is False
    captured = capsys.readouterr()
    assert "bad params" in captured.out
