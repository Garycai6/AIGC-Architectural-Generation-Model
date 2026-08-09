# 里程碑2:数据资产管线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立合成数据管线(synth → clean → validate),产出 4 风格 × 50 组 = 400 张带完整参数标签的小样本数据集,为里程碑3 的 LoRA+ControlNet 训练准备标准 imagefolder 格式数据。

**Architecture:** 顶层 `data/` 包三个独立模块:synth(复用 SimulatorGenerator 批量出图并写 metadata.jsonl)、clean(坏图/重复/坏标签剔除并重写索引)、validate(只读校验索引与磁盘一致性)。数据集采用类 HuggingFace imagefolder 格式:`images/` 扁平目录 + `metadata.jsonl` 索引。公开数据下载器本期只定契约不写代码。

**Tech Stack:** Python 3.11 + pytest + Pillow(已有)+ argparse(CLI)。

## Global Constraints

- 数据集格式:`data/datasets/<name>/images/*.png` + `data/datasets/<name>/metadata.jsonl`
- metadata.jsonl 每行一个 JSON 记录,字段:`id`(str)、`image`(相对路径,如 `images/synth_000001_facade.png`)、`source`(Literal["synth","web"],本期只有 "synth")、`kind`(Literal["facade","floorplan"])、`params`(完整 BuildingParams 快照)、`width_px`/`height_px`(int)
- **每条记录不含 created_at** —— 固定种子要求"两次生成完全一致",时间戳会破坏可复现性;这是对 spec 示例的刻意修正
- 复用现有 `SimulatorGenerator.generate(params, scheme_id, out_dir, lang)`,数据管线只当消费者,**不修改 generation/ 下任何代码**
- 同步入口用 `asyncio.run` 驱动 async 模拟器(CLI 与测试均在事件循环外)
- 测试输出一律走 pytest `tmp_path`,不得污染真实数据
- 保持现有依赖(Pillow/pydantic 已装),不新增依赖
- ruff:`line-length=100`,规则 E/F/I/UP/B;代码需 `ruff check` 与 `ruff format` 双绿
- commit 信息风格:中文,前缀 `feat:`/`test:`/`docs:`(遵循仓库现有风格)

---

### Task 1: data 包骨架 + synth.py 合成器

**Files:**
- Create: `data/__init__.py`
- Create: `data/synth.py`
- Test: `tests/test_synth.py`

**Interfaces:**
- Consumes: `generation.generators.SimulatorGenerator`(`await generate(params, scheme_id, out_dir, lang) -> GenerationArtifact`,已存在);`generation.params.model.STITLE_NAMES`、`BuildingParams`(已存在)
- Produces:
  - `data.synth.generate_dataset(out_dir: Path, per_style: int = 50, seed: int = 42) -> int` — 生成数据集,返回写入的记录条数(一条记录 = 一张图)
  - `data.synth._sample_params(rng: random.Random, style: str) -> BuildingParams` — 从合法值域抽样一组参数

- [ ] **Step 1: 创建 data 包**

`data/__init__.py` 空文件(hatch 已把 `data` 列入 wheel packages,见 pyproject.toml:38)。

- [ ] **Step 2: 写失败测试**

创建 `tests/test_synth.py`:

```python
import json
from pathlib import Path

from data.synth import _sample_params, generate_dataset
from generation.params.model import BuildingParams, STYLE_NAMES


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
            "id", "image", "source", "kind", "params", "width_px", "height_px",
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
```

- [ ] **Step 3: 跑测试确认失败**

Run: `uv run pytest tests/test_synth.py -v`
Expected: FAIL(ModuleNotFoundError: No module named 'data')

- [ ] **Step 4: 实现 data/synth.py**

```python
"""合成数据管线——复用模拟器批量出图,写标准 imagefolder 数据集。"""

import asyncio
import json
import random
import shutil
from pathlib import Path

from PIL import Image

from generation.generators import SimulatorGenerator
from generation.params.model import BuildingParams, STYLE_NAMES

MATERIALS = ["glass", "stone", "brick", "wood"]
ROOFS = ["flat", "pitched", "hipped"]
ENVIRONMENTS = ["urban", "suburb", "rural", "seaside"]


def _sample_params(rng: random.Random, style: str) -> BuildingParams:
    return BuildingParams(
        style=style,  # type: ignore[arg-type]
        floors=rng.randint(1, 6),
        width_m=round(rng.uniform(6.0, 20.0) * 2) / 2,
        depth_m=round(rng.uniform(5.0, 18.0) * 2) / 2,
        materials=rng.sample(MATERIALS, k=rng.randint(1, 3)),
        roof=rng.choice(ROOFS),
        environment=rng.choice(ENVIRONMENTS),
    )


def generate_dataset(out_dir: Path, per_style: int = 50, seed: int = 42) -> int:
    """按固定种子抽样参数,调模拟器批量出图,写 images/ + metadata.jsonl。

    返回写入的记录条数(一条记录 = 一张图)。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)
    rng = random.Random(seed)
    gen = SimulatorGenerator()
    records: list[dict] = []
    idx = 0
    for style in STYLE_NAMES:
        for _ in range(per_style):
            params = _sample_params(rng, style)
            idx += 1
            record_id = f"synth_{idx:06d}"
            tmp = out_dir / f".tmp_{record_id}"
            tmp.mkdir()
            try:
                art = asyncio.run(gen.generate(params, record_id, tmp, "zh"))
                for img in art.images:
                    src = tmp / img.url.rsplit("/", 1)[-1]
                    target = images_dir / f"{record_id}_{img.kind}.png"
                    shutil.copy(src, target)
                    with Image.open(target) as im:
                        width_px, height_px = im.size
                    records.append(
                        {
                            "id": record_id,
                            "image": f"images/{target.name}",
                            "source": "synth",
                            "kind": img.kind,
                            "params": params.model_dump(),
                            "width_px": width_px,
                            "height_px": height_px,
                        }
                    )
            finally:
                shutil.rmtree(tmp)
    with (out_dir / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="生成合成数据集")
    parser.add_argument("--out", type=Path, required=True, help="数据集输出目录")
    parser.add_argument("--per-style", type=int, default=50, help="每风格组数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    n = generate_dataset(args.out, per_style=args.per_style, seed=args.seed)
    print(f"生成 {n} 条记录 → {args.out}")
```

注意:`_sample_params` 的 style 参数以 `str` 传入,通过 `# type: ignore[arg-type]` 兼容 Literal;`BuildingParams` 的 pydantic 校验会在风格非法时抛错(作为抽样器自检)。

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest tests/test_synth.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add data/__init__.py data/synth.py tests/test_synth.py
git commit -m "feat: 合成数据管线 synth(复用模拟器批量出图 + 标准 imagefolder 格式)"
```

---

### Task 2: clean.py 清洗器

**Files:**
- Create: `data/clean.py`
- Test: `tests/test_clean.py`

**Interfaces:**
- Consumes: `data.synth.generate_dataset`(Task 1);`generation.params.model.BuildingParams`(已存在)
- Produces: `data.clean.clean_dataset(dataset_dir: Path) -> tuple[int, int]` — 就地清洗,返回 `(删除文件数, 移除记录数)`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_clean.py`:

```python
import json
from pathlib import Path

from data.clean import clean_dataset
from data.synth import generate_dataset


def _write_bad_label(ds: Path) -> None:
    """把第一条记录 params 改成非法风格。"""
    path = ds / "metadata.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["params"]["style"] = "baroque"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_clean_removes_missing_file(tmp_path: Path):
    ds = tmp_path / "ds"
    generate_dataset(ds, per_style=1, seed=1)
    rows = [json.loads(l) for l in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
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
    rows = [json.loads(l) for l in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
    (ds / rows[0]["image"]).unlink()
    clean_dataset(ds)
    after = [json.loads(l) for l in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
    for r in after:
        assert (ds / r["image"]).exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_clean.py -v`
Expected: FAIL(ModuleNotFoundError: No module named 'data.clean')

- [ ] **Step 3: 实现 data/clean.py**

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_clean.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add data/clean.py tests/test_clean.py
git commit -m "feat: 数据清洗器 clean(坏图/重复/坏标签剔除 + 索引重写)"
```

---

### Task 3: validate.py 校验器

**Files:**
- Create: `data/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `data.synth.generate_dataset`(Task 1)
- Produces: `data.validate.validate_dataset(dataset_dir: Path) -> bool` — 只读检查,通过返回 True;失败打印问题清单返回 False

- [ ] **Step 1: 写失败测试**

创建 `tests/test_validate.py`:

```python
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
    rows = [json.loads(l) for l in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
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
    rows = [json.loads(l) for l in (ds / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[0]["params"]["style"] = "baroque"
    (ds / "metadata.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    assert validate_dataset(ds) is False
    captured = capsys.readouterr()
    assert "bad params" in captured.out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_validate.py -v`
Expected: FAIL(ModuleNotFoundError: No module named 'data.validate')

- [ ] **Step 3: 实现 data/validate.py**

```python
"""校验器——只读检查数据集,不修改数据。训练脚本跑前必跑。"""

import json
from pathlib import Path

from PIL import Image

from generation.params.model import BuildingParams


def _load_records(metadata: Path) -> list[dict]:
    with metadata.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def validate_dataset(dataset_dir: Path) -> bool:
    problems: list[str] = []
    images_dir = dataset_dir / "images"
    metadata = dataset_dir / "metadata.jsonl"

    if not images_dir.is_dir():
        problems.append("missing images/ directory")
    if not metadata.exists():
        problems.append("missing metadata.jsonl")

    if metadata.exists():
        records = _load_records(metadata)
        if not records:
            problems.append("metadata.jsonl is empty")
        # 索引 → 磁盘
        indexed = set()
        for r in records:
            img = dataset_dir / r["image"]
            if not img.exists():
                problems.append(f"missing {r['image']}")
            indexed.add(Path(r["image"]).name)
            # 标签合法性
            try:
                BuildingParams(**r["params"])
            except Exception as e:
                problems.append(f"bad params {r['id']}: {e}")
            # 图片可读性 + 尺寸
            try:
                with Image.open(img) as im:
                    if im.size != (r["width_px"], r["height_px"]):
                        problems.append(
                            f"size mismatch {r['image']}: "
                            f"record {r['width_px']}x{r['height_px']} "
                            f"actual {im.size[0]}x{im.size[1]}"
                        )
            except Exception as e:
                problems.append(f"unreadable {r['image']}: {e}")
        # 磁盘 → 索引(孤儿文件)
        if images_dir.is_dir():
            disk_files = {p.name for p in images_dir.iterdir() if p.is_file()}
            for name in sorted(disk_files - indexed):
                problems.append(f"orphan {name}")

    for p in problems:
        print(p)
    if not problems:
        print(f"Dataset OK ({len(records)} images)")
        return True
    return False


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="校验数据集")
    parser.add_argument("--dir", type=Path, required=True, help="数据集目录")
    args = parser.parse_args()
    sys.exit(0 if validate_dataset(args.dir) else 1)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_validate.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add data/validate.py tests/test_validate.py
git commit -m "feat: 数据校验器 validate(索引-磁盘一致性 + 标签合法性只读检查)"
```

---

### Task 4: 接线与交付(Makefile + gitignore + demo 数据集)

**Files:**
- Modify: `Makefile`
- Modify: `.gitignore`
- Create: `docs/superpowers/plans/2026-08-09-milestone2-data-assets.md`(本计划存档)
- Create: `docs/gallery/smoke-test.md` 追加小节(验证记录)

**Interfaces:**
- Consumes: `data.synth.generate_dataset`、`data.clean.clean_dataset`、`data.validate.validate_dataset`(Task 1-3)

- [ ] **Step 1: Makefile 加三条命令**

在 `Makefile` 顶部 `.PHONY` 加 `data-synth data-clean data-validate`,末尾追加:

```make
data-synth:
	uv run python -m data.synth --out data/datasets/synth_demo --per-style 50 --seed 42

data-clean:
	uv run python -m data.clean --dir data/datasets/synth_demo

data-validate:
	uv run python -m data.validate --dir data/datasets/synth_demo
```

- [ ] **Step 2: .gitignore 忽略数据集**

在 `.gitignore` 的「数据与模型(不入库)」段追加一行:

```
data/datasets/
```

理由:400 张 PNG 是运行产物,不入库;代码(data/ 包)才入库。

- [ ] **Step 3: 生成 demo 数据集并校验**

Run: `make data-synth && make data-clean && make data-validate`
Expected: 生成 400 条记录;清洗 0 文件 0 记录;`Dataset OK (400 images)`

- [ ] **Step 4: 全量回归**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: 全部测试通过(原 56 + 新增 12 = 68 passed),ruff 双绿

- [ ] **Step 5: 记录验证结果**

在 `docs/gallery/smoke-test.md` 追加小节,记录:synth 生成 400 条记录、clean 幂等、validate 通过、全量 68 tests + ruff 绿。

- [ ] **Step 6: Commit**

```bash
git add Makefile .gitignore docs/superpowers/plans/2026-08-09-milestone2-data-assets.md docs/gallery/smoke-test.md
git commit -m "docs: 里程碑2 数据资产管线实施计划 + Makefile 命令 + 验证记录"
```

---

## Self-Review 记录

- **Spec 覆盖**:数据集格式(Task 1)、synth(Task 1)、clean(Task 2)、validate(Task 3)、CLI 入口(Task 1-3 各模块 `__main__`)、Makefile(Task 4)、gitignore/交付(Task 4)。下载器契约已在 spec 明确"本期不写代码",无需任务。
- **对 spec 的刻意修正**:每条记录去掉 `created_at` —— spec 自身要求"固定种子保证两次生成完全一致",时间戳会破坏可复现;以计划 Global Constraints 第 5 条注明。
- **类型一致性**:`generate_dataset(out_dir, per_style, seed) -> int`、`clean_dataset(dir) -> tuple[int,int]`、`validate_dataset(dir) -> bool` 三个签名在全部任务中一致;`_sample_params(rng, style)` 仅 Task 1 内部使用。
