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

# 里程碑 3 LoRA 训练管线验证记录 (2026-08-10)

- **training 包 6 模块**:config / dataset / export / train / verify / `__main__`(CLI 接线);纯逻辑层(config/dataset/export)本机可测,diffusers/torch 只出现在 train/verify(云端跑)
- 全量测试: **82 passed + 1 skipped**(`test_training_skip.py` 用 `pytest.importorskip("torch")` 自动跳过,本机无 torch);ruff check + format 双绿
- **训练范式**:标准 latent-space SDXL LoRA(VAE encode 像素 → latent 加噪/去噪 + 双 tokenizer 编码双 text encoder),云端 AutoDL 执行
- **云端执行命令**:`uv sync --extra gpu` 后 `uv run python -m training train --dataset-dir data/datasets/synth_demo --style modern --output-dir lora_out`(或 `make train-lora`);验证 `uv run python -m training verify --dataset-dir data/datasets/synth_demo --style modern --output-dir lora_out`
- **LoRA 产物**:4 风格各 1 个 .safetensors + 样例图;训练产物不入库(weight 文件、样例图)
- 接入网页是下期任务

# 里程碑 3.5 LoRA 接入网页验证记录 (2026-08-11)

- ApiGenerator 支持 lora_urls(风格→公网 URL),命中风格注入 lora_weights,缺省降级不注入
- Settings 新增 sdxl_model / lora_weights_dir;replicate 分支按 {dir}/{style}.tar 组装
- mock 单测:配置注入 / 未配置不注入 / 风格缺失降级 3 例 + Settings 字段 2 例 + 路由组装 1 例
- 全量回归: **88 passed + 1 skipped**(82 原有 + 6 新增);ruff check + format 双绿
- 真调留待人工:REPLICATE_API_TOKEN 本机非空可用,但**公网权重 URL 未就绪**——里程碑3 产物在云端 AutoDL,本机无 lora_out;接入前需将裸 .safetensors tar 打包重命名(lora.safetensors)上传至公网,并将 `sdxl_model` 指向带 `lora_weights` 字段的 ControlNet 模型(如 `fermatresearch/sdxl-controlnet-lora`)

# ApiGenerator 异步 prediction 改造验证记录 (2026-08-11)

- _call_sdxl 改 async,用 client.async_run(model, input, wait=300) 替代同步 client.run + to_thread
- SDK 内置异步轮询(async_create + prediction.async_wait),wait=300 解除 create 请求 60s read timeout
- mock 单测:async_run 调用 1 次、lora_weights 注入/降级逻辑不变、wait=300 断言
- 全量回归: 89 passed + 1 skipped;ruff check + format 双绿
- 真调:真调留待人工:REPLICATE_API_TOKEN 可用但公网 LoRA 权重 URL 未就绪

# LoRA tar 打包工具验证记录 (2026-08-11)

- training.pack 把 {style}.safetensors 打包成 {style}.tar(内含 lora.safetensors + special_params.json)
- CLI: python -m training package --output-dir <dir> --style <style> [--weight 1.0]
- mock 单测:tar 成员结构/扁平、weight 缩放、输入缺失抛错、CLI 分派
- 全量回归: 95 passed + 1 skipped;ruff check + format 双绿
- 用途:打包 tar 上传公网 URL 后,配 sdxl_model + lora_weights_dir 即可真调验证(留待人工)

# 前端 roof 控件验证记录 (2026-08-12)

- ParamForm 新增「屋顶」下拉(平顶/坡顶/四坡顶),默认「平顶」,替换硬编码 roof: "flat"
- 提交值用原始枚举值(flat/pitched/hipped);下拉显示 i18n 本地化标签(中文/英文)
- 浏览器验证:中文「屋顶」下拉默认「平顶」三选项;切 EN → Roof/Flat/Pitched/Hipped
- 端到端:同一参数仅 roof 不同,3 种屋顶效果图 PNG 字节全部不同(flat/pitched/hipped),roof 真实影响出图
- 后端零改动(roof 已有模拟器几何 + SDXL prompt 支持);全量回归 95 passed + 1 skipped
- 遗留:environment 控件暂缓(模拟器模式无视觉差异,留待真调验证阶段)

# 免费额度限制(Quota)验证记录 (2026-08-12)

- QuotaService:匿名访客每日额度计数(内存 dict,新日期自然重置),consume 返回剩余次数,超限不累加
- /generate 读 X-Visitor-Id 头;无头请求放行(向后兼容);超限返回 429 标准错误体 `{"detail":"今日免费额度已用完"}`
- GenerationResponse 新增 remaining_quota;前端 localStorage 持 visitor_id(UUID)+ 请求带头;429 抛 QuotaExhaustedError
- 前端展示「今日剩余生成次数:N」;429 显示「今日免费额度已用完」;i18n 中英双语
- 后端端到端(curl):同一访客 max=5,前 5 次 200 且 remaining_quota 递减 4/3/2/1/0,第 6 次 429;不同访客独立计数
- 前端编译:`tsc && vite build` 通过;vite dev server HTTP 200 服务正常
- 浏览器 UI 交互验证受限:本会话 preview 工具无法托管 vite+frontend(worktree 无前端代码,junction 使 vite 崩溃),留待人工浏览器确认「点击生成→剩余次数展示→超限提示」
- 全量回归:102 passed + 1 skipped;ruff check + format 双绿
- 遗留:付费解锁、持久化、登录用户维度计数均留待后续(本期仅免费额度限制)

# Quota 持久化验证记录 (2026-08-13)

- QuotaService 支持 storage_path(JSON 文件):构造加载,consume 后原子写盘(.tmp+os.replace),每 100 次写清理 7 天前记录
- 损坏容错:JSON 解析失败/形状错误 → 降级空 dict + warning;写盘失败记 error 不影响服务
- Settings.quota_storage_path 默认空=内存模式(向后兼容);非空启用持久化
- 端到端:QUOTA_STORAGE_PATH 启动 → 消费(remaining=4)→ 重启 → 再消费(remaining=3),计数跨重启保留;quota.json 内容正确
- 单测:持久化读写/重启恢复/损坏降级/内存模式不写盘/清理逻辑(相对日期防时间腐烂);路由级跨 app 重启保留
- 全量回归:110 passed + 1 skipped;ruff check + format 双绿
- 遗留:多 worker 跨进程同步(单 worker 部署够用);付费解锁仍留待后续

# 前端 environment 控件验证记录 (2026-08-13)

- ParamForm 新增「环境」下拉(城市/郊区/乡村/海滨),默认「郊区」,替换硬编码 environment: "suburb"
- 提交值用原始枚举值(urban/suburb/rural/seaside);下拉显示 i18n 本地化标签(中英双语 5 key)
- 后端端到端(curl):4 个合法 environment 值全部 200 正常出图,非法值 desert 422 拒绝
- 前端编译:`tsc && vite build` 通过,无 TS 类型错误
- 浏览器 UI 交互验证受限:本会话 preview 工具无法托管 vite+frontend(与 quota 功能同款环境限制),留待人工浏览器确认「环境下拉显示/EN 切换/请求 body 原始枚举值」
- 模拟器模式 environment 无视觉差异(已知特性,渲染器不读,真调阶段 SDXL prompt 生效)
- 后端零改动(environment 已有参数校验 + SDXL prompt 支持);全量回归 111 passed + 1 skipped

# 多供应商 Fal 验证记录 (2026-08-13)

- FalGenerator 独立类:镜像 ApiGenerator 的 facade-only 流程;线稿 upload_file 上传拿 URL 作 control_image_url;submit_async(start_timeout=300)+ handle.get() 拿 images[0].url 落盘
- 输入对齐 replicate:controlnet_conditioning_scale 0.5、steps 30、guidance 7.5、seed 42、1024×1024
- Settings 新增 fal_api_key/fal_model(默认空);image_provider 增 "fal" 分支,无 token 500;正式依赖 fal-client
- **依赖修正**:fal-client 约束 `>=0.7,<1.0` 锁定 0.14.1(1.0.0 删了 submit_async 的 timeout 参数,已改用 start_timeout;约束防未来 2.x 破坏)
- 条件图清理加 try/finally(失败也清理,防 Windows 重命名 FileExistsError)
- prompt.py 与 Generator 协议零改动;prompt 构造复用 build_prompt
- mock 单测:artifact 流程/上传+参数断言/缺客户端报错/失败清理 4 例 + 路由 2 例 + Settings 2 例
- 全量回归:119 passed + 1 skipped;ruff check + format 双绿
- 真调留待人工:.env 配 FAL_API_KEY + IMAGE_PROVIDER=fal(路由把 fal_api_key 注入 FAL_KEY 供 SDK 使用);真调时对比两供应商成本/质量
- 遗留:LoRA 注入(fal 的 loras 参数格式与 replicate 不同,对齐时再做);供应商自动故障切换;replicate_gen.py 同款 missing-finally 预存在未改

# LoRA 真调记录 (2026-08-17~08-20,卡点 + 结论)

## 已完成(成功)

- **云端训练成功**:4 风格 SDXL LoRA(现代/古典/欧式/北欧),每风格 ~46MB(`r=8` + attention-only 缩小体积)
- **LoRA 有效性已验证**:云端 `training verify` 出样例图 `modern_sample.png`,LoRA 学到风格(本地推理有效)
- **Replicate 无 LoRA 真调成功**:15.8s 出图,`fermatresearch/sdxl-controlnet-lora` 模型可用,链路通
- **代码修复落地**:`replicate.Client` 用 `api_token` 参数、`wait=60`(SDK 上限)、`httpx.Timeout(600)`、`condition_scale=0.5`

## 卡点(未解决):Replicate 容器 `pget` 无法解压 LoRA tar

- **现象**:带 LoRA 的真调全部失败,错误是 `pget` 下载+解压 tar 时报错:
  - gzip tar(Python tarfile 打包)→ `unexpected non-null byte in padding: 41`
  - gzip tar(GNU tar 打包)→ `unexpected non-null byte in padding: ff`
  - 纯 tar(未压缩)→ pget 不解压(只识别 gzip 魔数),把整个 tar 当文件 → `HeaderTooSmall`
- **已排查排除**:
  - tar 文件本身完好(本机 Python/GNU tar/gzip 都能正常解压,成员、键名都正确)
  - 不是文件大小(46MB 正常,下载 2 秒完成)
  - 不是 R2 托管(本机可正常下载;换 v2 路径绕过缓存仍失败)
  - 不是 LoRA 键名(已转成 diffusers processor 格式 `attn1.processor.to_q_lora.down.weight`)
  - 不是缺 `embeddings.pti`(已补占位)
- **根因判断**:pget(Go 的 gzip/tar 解压器)对 tar.gz 内部结构的校验与我们的 tar 不兼容,且对所有打包方式(gzip/纯 tar)都失败——疑似 pget 自身 bug 或与 R2 返回内容的兼容问题。**超出本机可控范围,无法继续调试。**

## 结论

- **LoRA 有效性已由云端 verify 样例图验证**(这是 LoRA 的核心价值,达成)
- **Replicate 网页注入 LoRA 受 `pget` 兼容性限制**,暂无法通过 URL 注入我们的 tar
- **替代路径**(如需网页注入):用 Fal(不依赖 pget)注入,或 Replicate 官方训练接口(内部生成的 LoRA 格式一定兼容)
- **代码状态**:训练 + 键名转换脚本(`training/convert_lora_keys.py`)已落地,后续若换路径可直接复用
- 遗留:`replicate_gen.py` 的 lora_urls 注入逻辑保留(未来用兼容 tar 即可触发)

# LoRA 真调突破 (2026-08-21,Replicate 官方训练路径打通)

## 卡点解决:改用 Replicate 官方训练接口

- **之前卡点**:自己训练(peft)的 LoRA tar,Replicate 容器 `pget` 无法解压(padding 错误/HeaderTooSmall)
- **突破**:改用 **Replicate 官方训练接口**(`stability-ai/sdxl` trainings API),它生成的权重**格式必然兼容 Replicate 加载**

## 成功流程

1. **训练**:`POST /v1/trainings`,`model=stability-ai/sdxl`,`input={input_images: <zip URL>, is_lora: true, resolution: 1024, max_train_steps: 1000}`,`destination=garycai6/archgen-modern-lora`
   - 训练图:41 张 modern facade 图打成 zip 上传 R2(`train-data/.tmp_modern_train.zip`)
   - **耗时约 5 分钟,成本约 $1.5~3**(训练成功,返回 `trained_model.tar` 权重 URL)
2. **注入**:`.env` 配 `LORA_WEIGHTS_URL=<trained_model.tar URL>`(新增字段,单 URL 形式,优先级高于 `LORA_WEIGHTS_DIR`)
3. **真调**:`/api/v1/generate` → **HTTP 200 成功出图**(facade 911KB 真图 + floorplan 模拟器线稿)

## 关键代码改动

- `Settings` 新增 `lora_weights_url`(单 URL 注入,适配 Replicate 官方训练产物)
- `generate.py`:优先用 `lora_weights_url`(单 URL,所有风格共用);否则 `lora_weights_dir` 目录拼接
- 测试:`test_generate_replicate_single_lora_url`(单 URL 分支)+ 修复 `test_generate_replicate_injects_lora_and_model` 隔离 .env

## 结论(更新)

- **LoRA 网页注入已走通**(Replicate 官方训练 + fermat 模型注入)
- 后续:训练其余 3 个风格(neoclassic/european/nordic,各约 $1.5~3),配对应权重 URL 即可
- **效果目检**:modern facade 911KB 真图已生成,需人工对比「有 LoRA vs 无 LoRA」确认风格化程度

