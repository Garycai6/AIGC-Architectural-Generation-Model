from pathlib import Path
from unittest.mock import patch

from training.train import main


def test_main_reports_no_data(tmp_path: Path, capsys):
    # 空数据集目录 -> 返回 1
    ds = tmp_path / "ds"
    ds.mkdir()
    (ds / "metadata.jsonl").write_text("", encoding="utf-8")
    rc = main(
        ["--dataset-dir", str(ds), "--style", "modern", "--output-dir", str(tmp_path / "out")]
    )
    assert rc == 1
    assert "无 facade 数据" in capsys.readouterr().out


def test_main_calls_train_loop(tmp_path: Path):
    # 构造含 modern facade 的最小数据集
    import json

    from PIL import Image

    ds = tmp_path / "ds"
    (ds / "images").mkdir(parents=True)
    Image.new("RGB", (64, 64), (0, 0, 0)).save(ds / "images" / "f.png")
    records = [
        {
            "id": "r1",
            "image": "images/f.png",
            "source": "synth",
            "kind": "facade",
            "width_px": 64,
            "height_px": 64,
            "params": {
                "style": "modern",
                "floors": 2,
                "width_m": 10.0,
                "depth_m": 8.0,
                "materials": ["brick"],
                "roof": "flat",
                "environment": "suburb",
            },
        }
    ]
    with (ds / "metadata.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps(records[0]) + "\n")
    with patch("training.train._train_loop") as mock_loop:
        rc = main(
            ["--dataset-dir", str(ds), "--style", "modern", "--output-dir", str(tmp_path / "out")]
        )
    assert rc == 0
    mock_loop.assert_called_once()
    assert (tmp_path / "out").is_dir()
