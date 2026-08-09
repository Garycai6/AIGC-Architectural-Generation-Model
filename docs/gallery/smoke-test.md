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

# 阶段 3 真调验证记录 (2026-08-09, token 充值后)
- 模型确认:`replicategithubwc/controlnet-sdxl`(model_type=canny),jagilley/controlnet-sdxl 已 404
- 真调链路通:模拟器线稿 → ControlNet(Canny)→ 1024×1024 真图(facade 1.25MB / floorplan 809KB)
- 关键修复:输出列表 `output[-1]` 才是真图,`output[0]` 是 Canny 边缘图(首次取错)
- ApiGenerator.generate 完整流程验证通过(两次 SDXL 调用,需加大 client timeout 到 300s)
- 已固化模型 ID 到 replicate_gen.py(版本哈希固定),测试 mock 反映真实输出结构
- **目检结论(2026-08-09)**:平面图糊/布局/门窗/尺寸全不对(SDXL 不适合平面图);立面细节错误多(模型幻觉)
- **决策修正**:平面图退回模拟器(准确程序化生成),效果图保留真模型;`_render_facade_sdxl` 只调一次 SDXL
- 验证通过:facade 1.25MB 真图 + floorplan 1.8KB 模拟器线稿
- **调优结论(2026-08-09)**:condition_scale 对比 0.5 vs 1.0——0.5 整体质量更好(更像效果图,有材质变化/细节);1.0 过约束致整面玻璃、无细节。**保留默认 0.5,不固化 1.0**;Canny 线稿边缘信息有限,scale 过高反而失真
- 效果图定位:对公众用户为「印象图」,细节非精确图纸;立面细节错误为 SDXL 固有幻觉,根治靠里程碑 3 LoRA 微调

# 阶段 4 前端语言切换验证记录 (2026-08-05)
- 默认中文界面:标题/表单/结果标签全中文
- 顶部「EN」按钮点击 → 全部文案变英文(Style/Floors/Width/Depth/Material/Generate)
- localStorage 持久化:刷新保持上次语言选择
- lang 同步传后端:英文状态生成 → 结果图标题 Facade/Floorplan(英文);中文状态 → 效果图/平面图
- 端到端:POST /api/v1/generate 200 + 结果图加载成功
- 全量测试 56 passed,ruff 全绿,前端 build 通过

# 里程碑 2 数据资产管线验证记录 (2026-08-09, 修复后重新生成)

- synth: `uv run python -m data.synth --out data/datasets/synth_demo --per-style 50 --seed 42` 生成 400 条记录,metadata.jsonl 索引完整
- 修复: `generate_dataset` 采样器按风格派生独立 RNG(`random.Random(f"{seed}:{style}")`),消除跨风格参数重复(Task 5)
- clean: `uv run python -m data.clean --dir data/datasets/synth_demo` 第一遍删除 75 条(同风格内参数域有限导致的哈希重复——模拟器几何形状简单,去重属正常行为);再跑 clean 输出 0 文件 0 记录,幂等
- validate: `uv run python -m data.validate --dir data/datasets/synth_demo` 输出 `Dataset OK (325 images)`,通过
- 全量回归: 69 passed (56 原有 + 12 新增 + 1 Task 5 唯一性测试); ruff check + format 双绿
- data/datasets/ 已加入 .gitignore,清洗后 325 张 PNG 不入库



