"""验证入口——加载训好的 LoRA 出样例图(云端执行)。

本机无 torch,diffusers 代码仅在云端运行;main 的参数解析部分本机可测。
"""

import sys

from training.config import CLI_ARGS, build_config
from training.dataset import make_prompt
from training.export import lora_output_path


def _parse_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="training.verify")
    for names, kwargs in CLI_ARGS:
        parser.add_argument(*names, **kwargs)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    cfg = build_config(args)
    lora_path = lora_output_path(cfg.output_dir, cfg.style)
    if not lora_path.exists():
        print(f"错误:LoRA 不存在 {lora_path}")
        return 1

    # 云端采样:加载 base SDXL + LoRA,出样例图
    import torch
    from diffusers import StableDiffusionXLPipeline

    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )
    pipe.to("cuda")
    pipe.load_lora_weights(str(lora_path))

    prompt = make_prompt(
        {
            "style": cfg.style,
            "floors": 2,
            "width_m": 10.0,
            "depth_m": 8.0,
            "materials": ["brick"],
            "roof": "flat",
            "environment": "suburb",
        }
    )
    out = cfg.output_dir / f"{cfg.style}_sample.png"
    image = pipe(
        prompt=prompt,
        num_inference_steps=30,
        guidance_scale=7.5,
        height=1024,
        width=1024,
    ).images[0]
    image.save(out)
    print(f"[verify] 样例图 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
