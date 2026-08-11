# 建筑 AIGC 生成模型 — LoRA 产物 tar 打包工具设计

日期:2026-08-11
状态:已确认

## 背景与定位

里程碑3.5 的 Replicate LoRA 注入已落地(mock 绿),但真调验证被卡在「公网权重 URL 未就绪」:Replicate 的 LoRA 注入需要 tar 打包(内含 `lora.safetensors`,可选 `special_params.json`),而训练产物是裸 `.safetensors`(`{style}.safetensors`,diffusers UNet LoRA state dict)。本期做一个 tar 打包工具,把训练产物转成可上传 Replicate 的格式,解锁人工真调验证。

## 关键事实(调研确认)

- 训练产物:`training` 包 `_train_loop` 用 `convert_state_dict_to_diffusers(unet.get_peft_state_dict())` + `save_file` 输出 `{output_dir}/{style}.safetensors`
- Replicate LoRA tar 要求:内含 `lora.safetensors`(权重重命名,扁平成员名),可选 `embeddings.pti` / `special_params.json`;裸 `.safetensors` 不直接被认
- `special_params.json` 记录 LoRA 权重缩放(Replicate 社区惯例,`{"weight": 1.0}`),便于真调时调 LoRA 强度
- 本机无 GPU、无 torch;打包是纯文件操作,本机可全测

## 架构

```
训练产物 {style}.safetensors
  └── training.pack.pack_lora(output_dir, style, weight_scale=1.0)
        └── tar.gz: lora.safetensors(重命名) + special_params.json({"weight": 1.0})
        └── 输出 {output_dir}/{style}.tar
```

CLI:`python -m training package --output-dir <dir> --style <style> [--weight 1.0]`

## 组件改动

### 1. `training/pack.py`(新,纯逻辑,无 torch 依赖)

- `pack_lora(output_dir: Path, style: str, weight_scale: float = 1.0) -> Path`
  - 输入路径 `output_dir / f"{style}.safetensors"`;不存在则 `raise FileNotFoundError(f"LoRA 权重不存在: {path}")`
  - 用 `tarfile.open(str(out), "w:gz")` 打包两个成员(成员名扁平,无目录前缀):
    - `lora.safetensors` ← 读原 .safetensors 字节写入
    - `special_params.json` ← `json.dumps({"weight": weight_scale})`
  - 返回输出路径 `output_dir / f"{style}.tar"`

### 2. `training/__main__.py`

- 分派新增 `package` 子命令(与 train/verify 并列)→ `training.pack.main`
- `training/pack.py` 提供 `main(argv: list[str] | None = None) -> int`,argparse 参数:
  - `--output-dir`(必填)— 含训练产物的目录
  - `--style`(必填)— 风格名(modern/neoclassic/european/nordic)
  - `--weight`(可选,默认 1.0)— LoRA 权重缩放
- 调用 `pack_lora`,打印 `[pack] 已打包 → {path}`

### 3. 测试 `tests/test_training_pack.py`

- `test_pack_lora_creates_tar`:临时目录造假的 `modern.safetensors` 字节 → `pack_lora(dir, "modern")` → 断言 `modern.tar` 存在,tarfile 读取内含 `lora.safetensors`(字节与原文件一致)与 `special_params.json`(json 解析后 `{"weight": 1.0}`),成员名均无目录前缀
- `test_pack_lora_weight_scale`:传 `weight_scale=0.5` → `special_params.json` 的 `weight == 0.5`
- `test_pack_lora_missing_weight_raises`:无 .safetensors → `FileNotFoundError`

## 测试策略

- mock 测试(本机无 GPU):pack_lora 纯逻辑全测
- 真调验证:人工——先用本工具打包 tar,上传公网 URL,再真调 replicate 注入(留待人工,记录 smoke-test.md)

## 交付边界

- 代码:`training/pack.py` + `__main__.py` 分派 + 测试
- 验证:mock 测试绿 + 全量回归 + ruff 双绿
- 产物:`python -m training package` 把训练产物转成 Replicate 可用的 tar.gz

## 与现有代码关系

- 不改:训练循环、`training/config.py`、`export.py`、网页 generate 链路
- 复用:`training/export.py` 的 `lora_output_path` 风格(命名约定 `{style}.safetensors`)
- 不引入新依赖(`tarfile`/`json` 为标准库)
- tar 产物不入库(公网 URL 引用,同 LoRA 权重策略)
