"""SDXL LoRA 训练入口——云端 AutoDL 执行。

本机不 import torch/diffusers:torch 代码在运行时 guarded import 内,本机只测
参数解析与数据准备部分(不进入训练循环)。
"""

import sys

from training.config import CLI_ARGS, build_config
from training.dataset import build_samples
from training.export import ensure_output_dir, lora_output_path


def _parse_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="training.train")
    for names, kwargs in CLI_ARGS:
        parser.add_argument(*names, **kwargs)
    return parser.parse_args(argv)


def _train_loop(cfg):
    """SDXL LoRA 训练循环——仅云端(torch 可用)执行。

    标准 diffusers LoRA 训练:加载 SDXL base,加 peft LoRA,用风格图做
    目标,输出 .safetensors。本机无 torch 不可达,测试 mock 掉。训练循环
    的正确性以云端跑通为准(本机无法验证 torch 行为)。
    """
    import torch
    from diffusers import AutoencoderKL, StableDiffusionXLPipeline
    from diffusers.optimization import get_scheduler
    from diffusers.utils import convert_state_dict_to_diffusers
    from peft import LoraConfig, get_peft_model
    from safetensors.torch import save_file
    from transformers import AutoTokenizer
    from PIL import Image

    # 1. 加载 SDXL base(仅训练,省显存:不加载 VAE decode)
    vae = AutoencoderKL.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", subfolder="vae"
    )
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        vae=vae, torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True,
    )
    pipe.to("cuda")
    pipe.vae.to(torch.float32)  # fp16 VAE 训练不稳定,回 float32

    tokenizer = AutoTokenizer.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0", subfolder="tokenizer"
    )
    text_encoder = pipe.text_encoder
    text_encoder_2 = pipe.text_encoder_2
    unet = pipe.unet
    unet.enable_gradient_checkpointing()

    # 2. 加 peft LoRA(unet)
    lora_config = LoraConfig(
        r=16, lora_alpha=32, target_modules=[
            "to_q", "to_k", "to_v", "to_out.0",
            "ff.net.0.proj", "ff.net.2",
        ],
        lora_dropout=0.0, bias="none",
    )
    unet = get_peft_model(unet, lora_config)

    # 3. 数据(每张图一个样本,prompt 用 build_prompt 构造)
    samples = build_samples(cfg.dataset_dir, cfg.style, cfg.resolution)
    images = [Image.open(s["image"]).convert("RGB") for s in samples]
    prompts = [s["prompt"] for s in samples]

    # 4. 优化器 + 调度器
    optimizer = torch.optim.AdamW(unet.parameters(), lr=cfg.learning_rate)
    steps = len(images) * cfg.epochs
    lr_scheduler = get_scheduler(
        "constant", optimizer=optimizer, num_warmup_steps=0,
        num_training_steps=steps,
    )

    # 5. 训练循环(逐张样本训练,epochs 次)
    unet.train()
    noise_scheduler = pipe.scheduler
    for epoch in range(cfg.epochs):
        for img, prompt in zip(images, prompts):
            pixel_values = torch.tensor(
                [img.resize((cfg.resolution, cfg.resolution))],
                dtype=torch.float32,
            ).permute(0, 3, 1, 2) / 127.5 - 1.0
            pixel_values = pixel_values.to(device="cuda", dtype=torch.float16)

            # 双 text encoder 编码 prompt
            text_inputs = tokenizer(
                prompt, padding="max_length", max_length=77, truncation=True,
                return_tensors="pt",
            )
            encoder_hidden_states = text_encoder(
                text_inputs.input_ids.to("cuda")
            )[0]
            text_inputs_2 = tokenizer(
                prompt, padding="max_length", max_length=77, truncation=True,
                return_tensors="pt",
            )
            encoder_hidden_states_2 = text_encoder_2(
                text_inputs_2.input_ids.to("cuda")
            )[0]

            # 加噪声 + denoising objective
            noise = torch.randn_like(pixel_values)
            timesteps = torch.randint(
                0, noise_scheduler.config.num_train_timesteps,
                (1,), device="cuda",
            ).long()
            noisy = noise_scheduler.add_noise(pixel_values, noise, timesteps)
            noise_pred = unet(
                noisy, timesteps,
                encoder_hidden_states=encoder_hidden_states,
                added_cond_kwargs={
                    "text_embeds": encoder_hidden_states_2,
                    "time_ids": torch.tensor(
                        [[cfg.resolution, cfg.resolution, 0, 0,
                          cfg.resolution, cfg.resolution]],
                        device="cuda",
                    ),
                },
            ).sample

            loss = torch.nn.functional.mse_loss(
                noise_pred.float(), noise.float(), reduction="mean"
            )
            loss.backward()
            optimizer.step()
            lr_scheduler.step()
            optimizer.zero_grad()

    # 6. 保存 LoRA .safetensors
    lora_path = lora_output_path(cfg.output_dir, cfg.style)
    unet_state = convert_state_dict_to_diffusers(unet.get_peft_state_dict())
    save_file(unet_state, lora_path)
    print(f"[training] 已保存 LoRA → {lora_path}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    cfg = build_config(args)
    ensure_output_dir(cfg.output_dir)
    samples = build_samples(cfg.dataset_dir, cfg.style, cfg.resolution)
    if not samples:
        print(f"错误:风格 {cfg.style} 无 facade 数据")
        return 1
    print(f"[training] {cfg.style}: {len(samples)} 张 facade 图")
    print(f"[training] 输出: {lora_output_path(cfg.output_dir, cfg.style)}")
    _train_loop(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
