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

    标准 diffusers latent-space LoRA 训练:加载 SDXL base,VAE encode 转
    latent,peft LoRA 微调 UNet,输出 .safetensors。本机无 torch 不可达,
    测试 mock 掉。训练循环的正确性以云端跑通为准(本机无法验证 torch 行为)。
    """
    import numpy as np
    import torch
    from diffusers import AutoencoderKL, StableDiffusionXLPipeline
    from diffusers.optimization import get_scheduler
    from diffusers.utils import convert_state_dict_to_diffusers
    from peft import LoraConfig, get_peft_model
    from PIL import Image
    from safetensors.torch import save_file
    from transformers import AutoTokenizer

    model_id = "stabilityai/stable-diffusion-xl-base-1.0"

    # 1. 加载 SDXL base(仅训练,省显存:不加载 VAE decode)
    vae = AutoencoderKL.from_pretrained(model_id, subfolder="vae")
    pipe = StableDiffusionXLPipeline.from_pretrained(
        model_id,
        vae=vae,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )
    pipe.to("cuda")
    # VAE 仅作 encode,不训练:float32 保 latent 精度,eval + 冻结
    vae.to("cuda")
    vae.eval()
    vae.requires_grad_(False)

    # 双 tokenizer:CLIP(text_encoder) 与 OpenCLIP(text_encoder_2) 词表不同
    tokenizer = AutoTokenizer.from_pretrained(model_id, subfolder="tokenizer", use_fast=False)
    tokenizer_2 = AutoTokenizer.from_pretrained(model_id, subfolder="tokenizer_2", use_fast=False)
    text_encoder = pipe.text_encoder
    text_encoder_2 = pipe.text_encoder_2
    text_encoder.eval()
    text_encoder.requires_grad_(False)
    text_encoder_2.eval()
    text_encoder_2.requires_grad_(False)
    unet = pipe.unet
    unet.enable_gradient_checkpointing()

    # 2. 加 peft LoRA(unet)
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=[
            "to_q",
            "to_k",
            "to_v",
            "to_out.0",
            "ff.net.0.proj",
            "ff.net.2",
        ],
        lora_dropout=0.0,
        bias="none",
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
        "constant",
        optimizer=optimizer,
        num_warmup_steps=0,
        num_training_steps=steps,
    )

    # 5. 训练循环(逐张样本训练,epochs 次)
    unet.train()
    noise_scheduler = pipe.scheduler
    for _epoch in range(cfg.epochs):
        for img, prompt in zip(images, prompts, strict=True):
            # 像素 -> latent(VAE encode,仅前向,不更新梯度)
            pixel_values = (
                torch.from_numpy(np.array(img.resize((cfg.resolution, cfg.resolution))))
                .float()
                .permute(2, 0, 1)[None]
                / 127.5
                - 1.0
            )
            pixel_values = pixel_values.to(device="cuda", dtype=torch.float32)
            latents = vae.encode(pixel_values).latent_dist.sample()
            latents = latents * vae.config.scaling_factor
            # VAE 用 fp32 保 latent 精度;UNet 权重是 fp16,喂入前统一转 fp16
            latents = latents.to(dtype=unet.dtype)

            # 双 text encoder 各用独立 tokenizer 编码 prompt
            text_inputs = tokenizer(
                prompt,
                padding="max_length",
                max_length=77,
                truncation=True,
                return_tensors="pt",
            )
            encoder_hidden_states = text_encoder(text_inputs.input_ids.to("cuda"))[0]
            text_inputs_2 = tokenizer_2(
                prompt,
                padding="max_length",
                max_length=77,
                truncation=True,
                return_tensors="pt",
            )
            encoder_hidden_states_2 = text_encoder_2(text_inputs_2.input_ids.to("cuda"))
            pooled_text_embeds = encoder_hidden_states_2.text_embeds
            encoder_hidden_states_2 = encoder_hidden_states_2.last_hidden_state

            # latent 上加噪 + denoising objective
            noise = torch.randn_like(latents)
            timesteps = torch.randint(
                0,
                noise_scheduler.config.num_train_timesteps,
                (1,),
                device="cuda",
            ).long()
            noisy_latents = noise_scheduler.add_noise(latents, noise, timesteps)
            # C1: SDXL UNet 期望 cross-attn 输入 dim=2048(CLIP 768 + OpenCLIP 1280)
            encoder_hidden_states = torch.cat(
                [encoder_hidden_states, encoder_hidden_states_2], dim=-1
            )
            noise_pred = unet(
                noisy_latents,
                timesteps,
                encoder_hidden_states=encoder_hidden_states,
                added_cond_kwargs={
                    "text_embeds": pooled_text_embeds,
                    "time_ids": torch.tensor(
                        [[cfg.resolution, cfg.resolution, 0, 0, cfg.resolution, cfg.resolution]],
                        device="cuda",
                        dtype=unet.dtype,
                    ),
                },
            ).sample

            loss = torch.nn.functional.mse_loss(noise_pred.float(), noise.float(), reduction="mean")
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
