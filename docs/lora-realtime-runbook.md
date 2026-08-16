# LoRA 真调 Runbook

> 目标:在云端 AutoDL 训练 4 风格 SDXL LoRA → 打包 → 上传公网 → 本机 Replicate 真调验证,确认 LoRA 能否根治效果图细节幻觉(里程碑 3 核心假设)。
> 适用:个人 + AI 协作,无 GPU 本机,云端租 4090。
> 状态:代码与管线已就绪(训练/打包/接入均已落地并测试),**只差云端执行 + 真调**。

## 前置(本机已就绪,逐项确认)

| 项 | 状态 | 确认命令 |
|---|---|---|
| 数据集 | 需重新生成(不入库) | `uv run python -m data.synth --out data/datasets/synth_demo --per-style 50 --seed 42` |
| 数据集校验 | 清洗后 325 张 | `uv run python -m data.clean --dir data/datasets/synth_demo` 再 `validate` |
| 训练代码 | 已落地 | `uv run pytest -q` → 119 passed + 1 skipped |
| 打包代码 | 已落地 | `uv run python -m training package --help` |

> **第一步先在本机重新生成数据集**(`data/datasets/` 被 gitignore,换机器/推送后为空)。

```bash
uv run python -m data.synth --out data/datasets/synth_demo --per-style 50 --seed 42
uv run python -m data.clean --dir data/datasets/synth_demo
uv run python -m data.validate --dir data/datasets/synth_demo   # 期望 Dataset OK
```

---

## 阶段 1:云端环境准备(AutoDL)

1. 租一台 **RTX 4090(24GB)** 实例(训练 SDXL LoRA 够用;若租 3090 也行,24GB 同样可用)。
2. 选镜像:含 CUDA 12.x + Python 3.11 的 PyTorch 镜像(避免自己装 CUDA)。
3. 开机后,把项目代码 + 数据集传到云端。**最小上传集**:不需要整个 repo,只要这几样:
   - `data/datasets/synth_demo/`(325 张 PNG + metadata.jsonl)
   - `training/` 目录(训练代码)
   - `generation/` 目录(prompt 构建器,training 依赖它)
   - `pyproject.toml` + `uv.lock`(或直接在云端 `pip install` 依赖)

   简单做法:整仓打包上传:
   ```bash
   # 本机,打包(排除 .venv/node_modules/.git)
   tar czf archgen-cloud.tar.gz \
     --exclude='.venv' --exclude='node_modules' --exclude='.git' \
     --exclude='.cache' --exclude='frontend' .
   # 上传到云端(AutoDL 有文件上传/OSS,或 scp)
   scp archgen-cloud.tar.gz root@<autodl-ip>:/root/autodl-tmp/
   ```

4. 云端解压 + 装依赖:
   ```bash
   cd /root/autodl-tmp && tar xzf archgen-cloud.tar.gz
   # 装 GPU 依赖(训练需要 torch/diffusers/peft/safetensors/transformers)
   pip install torch diffusers accelerate peft safetensors transformers pillow numpy
   # 或若装了 uv:uv sync --extra gpu
   ```

---

## 阶段 2:训练(4 风格,逐风格跑)

训练命令(每个风格一条,`--style` 换成对应风格):

```bash
python -m training train --dataset-dir data/datasets/synth_demo --style modern --output-dir lora_out
python -m training train --dataset-dir data/datasets/synth_demo --style neoclassic --output-dir lora_out
python -m training train --dataset-dir data/datasets/synth_demo --style european --output-dir lora_out
python -m training train --dataset-dir data/datasets/synth_demo --style nordic --output-dir lora_out
```

**每步验证点:**
- 输出 `[training] <style>: N 张 facade 图`(N ≈ 75~82,4 风格各一)
- 结束输出 `[training] 已保存 LoRA → lora_out/<style>.safetensors`
- `ls -la lora_out/` 确认 4 个 `.safetensors` 都在,大小非 0(通常几十 MB)

**训练参数(默认值,一般不改):**
- `--resolution 1024`、`--epochs 50`、`--learning-rate 1e-4`、`--train-batch-size 1`、`--seed 42`
- 若 24GB 显存不够(batch 1 + 1024 分辨率通常够),可先降到 `--resolution 768` 试跑

---

## 阶段 3:验证(出样例图目检)

```bash
python -m training verify --dataset-dir data/datasets/synth_demo --style modern --output-dir lora_out
```

**验证点:**
- 输出 `[verify] 样例图 → lora_out/modern_sample.png`
- **目检 `modern_sample.png`**:与「无 LoRA 的 SDXL」对比,风格是否更贴近训练数据(现代简约的窗型/檐口/配色)。这是 LoRA 有效性的第一道判断——若样例图与普通 SDXL 无差异,说明 LoRA 没学进去,需回查训练。

4 风格各验一次(换 `--style`)。

---

## 阶段 4:打包 tar

训练产物是裸 `.safetensors`,Replicate 的 LoRA 注入要求 tar 内权重重命名为 `lora.safetensors`。打包:

```bash
python -m training package --output-dir lora_out --style modern
python -m training package --output-dir lora_out --style neoclassic
python -m training package --output-dir lora_out --style european
python -m training package --output-dir lora_out --style nordic
```

**验证点:**
- 输出 `[pack] 已打包 → lora_out/<style>.tar`
- `ls -la lora_out/*.tar` 确认 4 个 tar 都在

---

## 阶段 5:上传公网

把 4 个 `lora_out/*.tar` 传到**可公网访问的 URL**(Replicate 的 lora_weights 字段需要 URL 下载)。选项:

1. **AutoDL 文件下载链接**(临时,有时效,仅测试用)
2. **对象存储**(阿里 OSS / 腾讯 COS / Cloudflare R2 等,推荐,稳定公网 URL)
3. **GitHub Release 附件**(免费、稳定,适合几十 MB 的 tar)

上传后拿到 4 个 URL,格式形如:
- `https://<你的域名>/lora/modern.tar`
- `https://<你的域名>/lora/neoclassic.tar`
- `https://<你的域名>/lora/european.tar`
- `https://<你的域名>/lora/nordic.tar`

**验证点:** 浏览器/curl 能直接下载:`curl -I <url>` 返回 200。

---

## 阶段 6:本机配置 + 真调

**关键前置:** 当前默认 `SDXL_MODEL`(`replicategithubwc/controlnet-sdxl`)**不含 `lora_weights` 字段**,注入 LoRA 需换模型。`.env` 配置:

```bash
# .env
REPLICATE_API_TOKEN=<你的 token>
IMAGE_PROVIDER=replicate
SDXL_MODEL=fermatresearch/sdxl-controlnet-lora   # 带 lora_weights 字段的 ControlNet 模型
LORA_WEIGHTS_DIR=https://<你的域名>/lora          # 按 {dir}/{style}.tar 组装
```

> 注意:`fermatresearch/sdxl-controlnet-lora` 是记忆里记录的候选,但**社区模型可能已下线**(阶段 3 就遇到过)。真调时若 404,需在 Replicate 找一个「带 lora_weights 字段 + ControlNet Canny」的 SDXL 模型替换 `SDXL_MODEL`。这是本阶段唯一的外部不确定性。

启动 + 真调:

```bash
uv run archgen-api
# 前端选 modern 风格 → 生成 → 目检效果图
curl -s -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" -H "X-Visitor-Id: lora-test" \
  -d '{"params":{"style":"modern","floors":3,"width_m":10,"depth_m":8,"materials":["glass"],"roof":"flat","environment":"suburb"},"lang":"zh"}'
```

---

## 验收标准(里程碑 3 核心假设)

| 判据 | 结论 |
|---|---|
| modern 风格效果图比「无 LoRA」更贴训练风格(窗型/檐口/配色) | ✅ LoRA 生效,假设成立 |
| 4 风格各自风格化明显、互相可区分 | ✅ 可上线 |
| 细节幻觉(门窗错乱/结构错误)显著减少 | ✅ 根治达成 |
| 样例图与普通 SDXL 无差异 | ❌ LoRA 没学进去,回查训练(学习率/epochs/数据) |

**回退路径:** 若 LoRA 效果不佳,优先调 `--epochs`(50 可能过拟合/欠拟合)、`--learning-rate`、或检查数据集去重是否过度(325 张偏少,可能需 `--per-style` 提到 100 重生成)。

---

## 时间与成本预估(供决策)

- AutoDL 4090 租用:约 ¥2~3/小时
- 4 风格训练:每风格约 15~30 分钟(82 张 × 50 epochs × batch 1),总计 1~2 小时
- 上传/打包:忽略不计
- Replicate 真调:每次生成约 ¥0.01~0.05

**总成本:约 ¥10 以内一次完整真调。**
