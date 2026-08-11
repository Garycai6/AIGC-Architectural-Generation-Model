import json
import tarfile
from pathlib import Path

import pytest

from training.pack import pack_lora


def _write_fake_lora(
    tmp_path: Path, style: str = "modern", data: bytes = b"fake-safetensors-bytes"
):
    (tmp_path / f"{style}.safetensors").write_bytes(data)
    return tmp_path


def test_pack_lora_creates_tar(tmp_path: Path):
    out = _write_fake_lora(tmp_path)
    result = pack_lora(out, "modern")

    assert result == out / "modern.tar"
    assert result.exists()
    with tarfile.open(result, "r:gz") as tar:
        names = tar.getnames()
        assert "lora.safetensors" in names
        assert "special_params.json" in names
        # 成员名扁平,无目录前缀
        assert all("/" not in n and "\\" not in n for n in names)
        assert tar.extractfile("lora.safetensors").read() == b"fake-safetensors-bytes"
        special = json.loads(tar.extractfile("special_params.json").read())
        assert special == {"weight": 1.0}


def test_pack_lora_weight_scale(tmp_path: Path):
    out = _write_fake_lora(tmp_path)
    pack_lora(out, "modern", weight_scale=0.5)

    with tarfile.open(out / "modern.tar", "r:gz") as tar:
        special = json.loads(tar.extractfile("special_params.json").read())
    assert special == {"weight": 0.5}


def test_pack_lora_missing_weight_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        pack_lora(tmp_path, "nordic")
