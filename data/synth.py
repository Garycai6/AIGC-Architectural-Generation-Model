"""合成数据管线——复用模拟器批量出图,写标准 imagefolder 数据集。"""

import asyncio
import json
import random
import shutil
from pathlib import Path

from PIL import Image

from generation.generators import SimulatorGenerator
from generation.params.model import STYLE_NAMES, BuildingParams

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
    gen = SimulatorGenerator()
    records: list[dict] = []
    idx = 0
    for style in STYLE_NAMES:
        style_rng = random.Random(f"{seed}:{style}")
        for _ in range(per_style):
            params = _sample_params(style_rng, style)
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
                            "id": target.stem,
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
