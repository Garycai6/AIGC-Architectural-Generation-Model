from pathlib import Path

from training.export import ensure_output_dir, lora_filename, lora_output_path


def test_lora_filename():
    assert lora_filename("modern") == "modern.safetensors"
    assert lora_filename("neoclassic") == "neoclassic.safetensors"


def test_lora_output_path():
    p = lora_output_path(Path("out"), "nordic")
    assert p == Path("out") / "nordic.safetensors"


def test_ensure_output_dir_creates(tmp_path: Path):
    out = ensure_output_dir(tmp_path / "nested" / "out")
    assert out.is_dir()


def test_ensure_output_dir_idempotent(tmp_path: Path):
    out = ensure_output_dir(tmp_path / "out")
    assert ensure_output_dir(tmp_path / "out") == out
