# LoRA 产物 tar 打包工具 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `training.pack` 子命令,把训练产物 `{style}.safetensors` 打包成 Replicate 可用的 tar.gz(内含 `lora.safetensors` + `special_params.json`),解锁人工真调验证。

**Architecture:** 纯逻辑 `training/pack.py`(无 torch 依赖,本机可测),`pack_lora` 读 `{output_dir}/{style}.safetensors`,用 `tarfile` 打包为 `{output_dir}/{style}.tar`(成员扁平)。`training/__main__.py` 分派 `package` 子命令。

**Tech Stack:** Python 3.11 / tarfile / json(标准库)/ pytest + ruff(E/F/I/UP/B)。

## Global Constraints

- ruff:`line-length = 100`,`select = ["E", "F", "I", "UP", "B"]`,check + format 双绿
- commit 前缀:`feat:` / `fix:` / `docs:`;消息用中文
- 本机无 GPU、无 torch;打包是纯文件操作,不 import torch/diffusers
- 不改:训练循环、`training/config.py`、`training/export.py`、网页 generate 链路
- 复用命名约定:`training/export.py` 的 `lora_output_path`(`{style}.safetensors`)
- tar 产物不入库(公网 URL 引用,同 LoRA 权重策略)
- 设计文档 `docs/superpowers/specs/2026-08-11-lora-tar-package-design.md` 为唯一需求来源

---

### Task 1: pack_lora 纯逻辑 + 单测

**Files:**
- Create: `training/pack.py`
- Create: `tests/test_training_pack.py`

**Interfaces:**
- Consumes: 无(独立纯逻辑)
- Produces:
  - `pack_lora(output_dir: Path, style: str, weight_scale: float = 1.0) -> Path` — 打包 `{output_dir}/{style}.safetensors` → `{output_dir}/{style}.tar`,输入缺失抛 `FileNotFoundError`

- [ ] **Step 1: 写失败测试(tests/test_training_pack.py)**

```python
from pathlib import Path
import json
import tarfile

import pytest

from training.pack import pack_lora


def _write_fake_lora(tmp_path: Path, style: str = "modern", data: bytes = b"fake-safetensors-bytes"):
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_training_pack.py -v`
Expected: FAIL(ModuleNotFoundError: training.pack)

- [ ] **Step 3: 实现 training/pack.py**

```python
"""LoRA 产物打包——训练 .safetensors 转 Replicate 可用的 tar.gz。纯逻辑,不 import torch。"""

import json
import tarfile
from pathlib import Path

from training.export import lora_output_path


def pack_lora(output_dir: Path, style: str, weight_scale: float = 1.0) -> Path:
    """把 {style}.safetensors 打成 {style}.tar(内含 lora.safetensors + special_params.json)。

    Replicate 的 LoRA 注入要求 tar 内权重重命名为 lora.safetensors;special_params.json
    记录 LoRA 权重缩放(社区惯例)。成员名扁平,无目录前缀。
    """
    src = lora_output_path(output_dir, style)
    if not src.exists():
        raise FileNotFoundError(f"LoRA 权重不存在: {src}")

    out = output_dir / f"{style}.tar"
    with open(src, "rb") as f, tarfile.open(out, "w:gz") as tar:
        data = f.read()
        info = tarfile.TarInfo(name="lora.safetensors")
        info.size = len(data)
        tar.addfile(info, __import__("io").BytesIO(data))

        special = json.dumps({"weight": weight_scale}, separators=(",", ":")).encode()
        info = tarfile.TarInfo(name="special_params.json")
        info.size = len(special)
        tar.addfile(info, __import__("io").BytesIO(special))
    return out
```

注意:实现可简化——用 `tar.addfile` 时直接构造 `io.BytesIO`(顶部 `import io` 替代 inline `__import__("io")`),保持清晰。以上为逻辑骨架,实现时把 `io` 放顶部 import。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_training_pack.py -v`
Expected: 3 个 PASS

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check training/pack.py tests/test_training_pack.py && uv run ruff format training/pack.py tests/test_training_pack.py && uv run ruff check training/pack.py tests/test_training_pack.py`
Expected: 双绿

```bash
git add training/pack.py tests/test_training_pack.py
git commit -m "feat: training.pack 把 LoRA .safetensors 打包成 Replicate 可用的 tar.gz"
```

---

### Task 2: __main__.py 分派 package 子命令

**Files:**
- Modify: `training/__main__.py:6-23`
- Create: `tests/test_training_pack.py`(追加 CLI 测试)

**Interfaces:**
- Consumes: `training.pack.main(argv) -> int`(Task 1 需实现,见 Step 3)
- Produces: `python -m training package --output-dir <dir> --style <style> [--weight 1.0]` 可用

- [ ] **Step 1: 在 training/pack.py 加 main(argv) -> int**

在 `pack_lora` 之后追加:

```python
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="training.pack")
    parser.add_argument("--output-dir", required=True, help="含训练产物的目录")
    parser.add_argument("--style", required=True, help="风格名(modern/neoclassic/european/nordic)")
    parser.add_argument("--weight", type=float, default=1.0, help="LoRA 权重缩放(默认 1.0)")
    args = parser.parse_args(argv)

    path = pack_lora(Path(args.output_dir), args.style, args.weight)
    print(f"[pack] 已打包 → {path}")
    return 0
```

在文件顶部 `from pathlib import Path` 已 import,无需重复。

- [ ] **Step 2: 修改 training/__main__.py**

```python
    if sys.argv[1] not in ("train", "verify", "package"):
        print(__doc__)
        return 1
    sub, rest = sys.argv[1], sys.argv[2:]
    if sub == "train":
        from training.train import main as train_main

        return train_main(rest)
    if sub == "package":
        from training.pack import main as pack_main

        return pack_main(rest)
    from training.verify import main as verify_main

    return verify_main(rest)
```

- [ ] **Step 3: 追加 CLI 测试(tests/test_training_pack.py 末尾)**

```python
def test_pack_main_cli(tmp_path: Path, capsys):
    _write_fake_lora(tmp_path)
    from training.pack import main

    rc = main(["--output-dir", str(tmp_path), "--style", "modern"])
    assert rc == 0
    assert (tmp_path / "modern.tar").exists()
    out = capsys.readouterr().out
    assert "[pack] 已打包" in out


def test_pack_main_missing_style_raises(tmp_path: Path):
    from training.pack import main

    with pytest.raises(FileNotFoundError):
        main(["--output-dir", str(tmp_path), "--style", "nordic"])


def test_main_dispatch_package(tmp_path: Path, capsys):
    import subprocess
    import sys

    _write_fake_lora(tmp_path)
    code = subprocess.call(
        [sys.executable, "-m", "training", "package",
         "--output-dir", str(tmp_path), "--style", "modern"],
        cwd=str(tmp_path),
    )
    assert code == 0
    assert (tmp_path / "modern.tar").exists()
```

注意:`test_main_dispatch_package` 用 `subprocess` 跑 `python -m training` 验证分派。若 subprocess 在本机环境跑不通(如 cwd 需为项目根),实现时调整 cwd 为项目根(`Path(__file__).parents[1]`),保持测试真实但不脆。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_training_pack.py -v`
Expected: 全部 PASS(3 逻辑 + 3 CLI = 6)

- [ ] **Step 5: 全量回归 + ruff 双绿**

Run: `uv run pytest -q`
Expected: 89 + 3(逻辑)+ 3(CLI)= **95 passed + 1 skipped**(若 subprocess 测试跑通;如遇环境问题记录并调整)
Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 双绿

- [ ] **Step 6: 提交**

```bash
git add training/pack.py training/__main__.py tests/test_training_pack.py
git commit -m "feat: python -m training package 子命令打包 LoRA tar"
```

---

### Task 3: smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`

**Interfaces:**
- Consumes: Task 1-2 全部改动
- Produces: 冒烟验证记录

- [ ] **Step 1: 追加记录**

```markdown
# LoRA tar 打包工具验证记录 (2026-08-11)

- training.pack 把 {style}.safetensors 打包成 {style}.tar(内含 lora.safetensors + special_params.json)
- CLI: python -m training package --output-dir <dir> --style <style> [--weight 1.0]
- mock 单测:tar 成员结构/扁平、weight 缩放、输入缺失抛错、CLI 分派
- 全量回归: 95 passed + 1 skipped;ruff check + format 双绿
- 用途:打包 tar 上传公网 URL 后,配 sdxl_model + lora_weights_dir 即可真调验证(留待人工)
```

- [ ] **Step 2: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: LoRA tar 打包工具验证记录(全量回归 + 真调前置已就绪)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| `pack_lora(output_dir, style, weight_scale=1.0) -> Path` | Task 1 | 3 个逻辑测试 |
| tar 内含 `lora.safetensors` + `special_params.json`,成员扁平 | Task 1 | `test_pack_lora_creates_tar` |
| `special_params.json` 的 weight 值正确 | Task 1 | `test_pack_lora_weight_scale` |
| 输入缺失抛 `FileNotFoundError` | Task 1 | `test_pack_lora_missing_weight_raises` |
| `__main__.py` 分派 `package` 子命令 | Task 2 | `test_main_dispatch_package` |
| `--weight` 可选参数默认 1.0 | Task 2 | `test_pack_main_cli` + 实现 |
| 本机无 torch 可全测 | 全计划 | pack.py 无 torch import |
| 不改训练循环/export/config/网页链路 | 全计划 | diff 检查 |
| tar 产物不入库 | 全计划 | .gitignore 不涉及,仅公网引用 |
