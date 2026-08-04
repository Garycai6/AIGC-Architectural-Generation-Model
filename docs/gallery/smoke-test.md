# 阶段 0 冒烟验证记录
- 后端 /health 通过 (2026-08-04)
- 前端页面加载通过
- /api/v1/generate 返回 scheme_id 与占位描述

# 阶段 2 冒烟验证记录 (2026-08-04)
- 后端 /health 通过,uvicorn 正常启动
- POST /api/v1/generate 返回 2 张图 URL(效果图 + 平面图),scheme_id 正常
- /images/{scheme_id}/facade.png 与 floorplan.png 均可访问(HTTP 200, image/png),PNG magic bytes 校验通过
- 不同风格(modern/neoclassic/nordic)、不同层数(2/3/6)、不同语言(zh/en)参数均正常出图
- 非法参数(style=baroque)返回 422
- 全量测试 33 passed;ruff check + format 全绿
