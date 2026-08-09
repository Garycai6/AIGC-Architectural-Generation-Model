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

# 阶段 2.5 冒烟验证记录 (2026-08-05)
- 屋顶差异化:4 风格 × 3 屋顶(flat/pitched/hipped)共 12 组合,同风格不同屋顶 PNG 字节全部不同
- 风格差异化:3 屋顶 × 4 风格(modern/neoclassic/european/nordic),同屋顶不同风格 PNG 字节全部不同
- 视觉元素生效:写实屋顶(屋脊/坡面/山墙)、檐口+山花(neoclassic/european)、拱形窗(european)、风格配色叠加
- 非法参数(style=baroque)返回 422
- 全量测试 45 passed;ruff check + format 全绿

# 阶段 3 冒烟验证记录 (2026-08-09)
- 阶段3: ApiGenerator(SDXL+ControlNet)实现,线稿作条件图,双产出走真模型
- 阶段3: mock 测试通过(路由切换 + ApiGenerator 两次调用),真调验证(跳过——REPLICATE_API_TOKEN 未配置)
- 阶段3: 全量测试 56 passed,ruff 全绿
