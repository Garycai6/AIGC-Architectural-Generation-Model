# 建筑 AIGC 生成模型 (ArchGen)

通过 Stable Diffusion/Transformer 微调,输入建筑参数自动生成建筑方案(效果图+平面图)的 SaaS 产品。

## 开发

```bash
make setup    # 安装依赖(uv sync + npm install)
make test     # 跑 pytest
make lint     # ruff 检查
```

详见 `docs/superpowers/plans/` 下的实施计划。
