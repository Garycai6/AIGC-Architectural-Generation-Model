# 阶段 2:生成服务 — 设计规格

日期：2026-08-04
状态：已确认
前置：阶段 0(Monorepo 骨架 + BuildingParams + FastAPI/React 空壳)已完成

## 背景与定位

阶段 0 已建立骨架:`/api/v1/generate` 目前只返回 `scheme_id + description + 空 images`。阶段 2 的目标是**接通出图闭环**:输入建筑参数 → 本地程序化生成效果图(3/4 透视立面)与平面示意 → 静态文件交付 → 前端表单下方展示。此为里程碑 1「网页产品框架(最小闭环)」的核心打通。

**本阶段验证期采用"模拟器先"策略**:本地确定性程序化绘图(零 GPU、零 API key、测试确定),同时立起 `Generator` 抽象接口,为后续 `ApiGenerator`(Replicate/Fal)与真实模型无缝切换。护城河「参数→程序化线稿」代码在本阶段沉淀。

## 关键决策(已确认)

| 决策点 | 结论 |
|---|---|
| 出图方式 | 模拟器先(本地确定性绘图);API 适配器接口先搭不接真 API |
| 线稿深度 | 立面文法 + 3/4 透视(带体量感) |
| 平面图 | 简单平面示意(外墙 + 内墙网格 + 房间标签) |
| 房间标签 | 中英双语(跟随 `lang` 参数) |
| 图片交付 | 静态文件 URL,落盘 `cache_dir/{scheme_id}/` |
| 验证边界 | 专注出图闭环;NL 解析 / 真 API / 额度逻辑全部推后 |
| 前端展示 | 表单下方并排展示效果图 + 平面图 |
| 生成器抽象 | `Generator` 接口:`SimulatorGenerator` 与未来 `ApiGenerator` 实现同一接口 |

## 架构

新增 `generation/generators/` 包,沿用现有 `generation/params/` 结构。核心逻辑分层,单元职责单一。

```
generation/
├── params/model.py          # 已有:BuildingParams
├── generators/
│   ├── __init__.py          # 导出 Generator, SimulatorGenerator
│   ├── base.py              # Generator 抽象接口 + GenerationArtifact + ImageRef
│   └── simulator/
│       ├── __init__.py
│       ├── renderer.py      # 编排:组装各模块 → 落盘 → GenerationArtifact
│       ├── facade.py        # 立面文法(护城河:参数 → 2D 线框)
│       ├── perspective.py   # 3/4 等轴透视投影(带体量感)
│       └── floorplan.py     # 简单平面示意
```

## 生成器抽象(base.py)

```python
class ImageRef(BaseModel):
    kind: Literal["facade", "floorplan"]   # 产出类型
    url: str                                # 供前端 <img src> 的相对 URL

class GenerationArtifact(BaseModel):
    scheme_id: str
    images: list[ImageRef]

class Generator(Protocol):
    """生成器契约——模拟器与未来 API/真实模型共用,网页层零改动。"""
    async def generate(
        self, params: BuildingParams, scheme_id: str, out_dir: Path
    ) -> GenerationArtifact: ...
```

- `SimulatorGenerator`(本阶段实现):在 `asyncio.to_thread` 中同步绘制,避免阻塞事件循环
- 未来 `ApiGenerator`(Replicate/Fal):实现同一接口,异步调用远端
- 渲染器是同步纯函数(Pillow),线程池执行;FastAPI 事件循环不被绘图阻塞

## 护城河:立面文法(facade.py)

输入 `BuildingParams`,输出确定性 2D 线框(后续为透视投影、再后续直接喂 ControlNet 的输入):

- **体量轮廓**:`width_m × (floors × 3.2m)` 外墙边界,按输出画布缩放
- **分层线**:每层一条水平带,含层间线脚(细横线)
- **开窗网格**:按 `宽度/层高` 推导窗列数,窗 = 矩形 + 十字窗棂;底层/顶部有差异
- **材质配色**:`materials` → 调色板(glass/stone/brick/wood 各有主色/辅色)
- **风格差异**(确定性规则):
  - modern → 横向长窗 + 无檐口
  - neoclassic → 对称窗 + 檐口线
  - european → 竖窗 + 山花(三角楣)
  - nordic → 木色 + 坡屋顶线
- **屋顶**:flat 无;pitched/hipped → 三角形/梯形轮廓线

输出:`FacadeWireframe`(顶点/线段/填充块/配色)的数据结构,与绘图解耦。

## 3/4 透视(perspective.py)

- 手写等轴/斜轴投影矩阵,将正立面 2D 线框旋转到 3/4 视角
- **带体量感**:绘制侧壁 + 顶面,形成"效果图"观感,而非纯正立面投影
- 纯数学变换,无外部依赖

## 平面示意(floorplan.py)

- 外墙矩形(按 `width_m × depth_m` 比例缩放)
- 内墙网格:按楼层数/面积切分房间,画内墙线
- 房间标签:中英双语,跟随 `lang`(zh:厨房/卧室/客厅;en:Kitchen/Bedroom/Living)
- 简化但可见

## 渲染编排与落盘(renderer.py)

- `asyncio.to_thread` 内同步绘制
- 输出 PNG 到 `cache_dir/{scheme_id}/facade.png`、`floorplan.png`
- 返回 `GenerationArtifact`

## API 变更

`/api/v1/generate`(backend/app/api/generate.py):
- 注入 `Generator`(测试可替换为 fake)
- 调 `await generator.generate(params, scheme_id, out_dir)` → 非空 `images` URL
- 保留 `description`(DeepSeek 分支不变)
- `GenerationResponse.images` 从 `list[str]` 承载 URL 列表

**静态文件服务**:`StaticFiles(directory=cache_dir)` 挂载,`GET /images/{scheme_id}/facade.png`、`/floorplan.png` 返回 PNG。阶段 2 无鉴权需求。

## 前端变更

`ParamForm` 提交后:
- 不再 console.log → `fetch` 调 `/api/v1/generate`
- 响应 `images` → 表单下方并排 `<img>` 展示效果图 + 平面图
- 用现有 i18n 键补充文案(zh/en)

## 错误处理

- 渲染失败 → `HTTPException(500)` + 结构化消息,前端显示可读错误
- 参数校验由 pydantic 兜底(422),现有测试已覆盖
- 所有生成产物落盘 `cache_dir`,已被 `.gitignore` 覆盖(不入库)

## 测试策略

- **单元(确定性)**:
  - facade 文法:参数 → 线框指令(体量/窗格/屋顶存在)
  - perspective 投影:顶点变换正确(旋转/缩放)
  - floorplan:外墙矩形 + 内墙 + 标签存在
- **渲染冒烟**:
  - PNG 存在、非空、尺寸正确
- **API**:
  - `POST /api/v1/generate` 返回 200 + 非空 `images` URL
  - `GET /images/{scheme_id}/facade.png` 返回 200
- **前端**:`npm run build` 通过(TypeScript 编译)

## 明确排除(本阶段不做)

- ❌ Replicate/Fal 真 API 调用(`ApiGenerator` 仅留接口与桩)
- ❌ NL 自然语言解析接入(前端自然语言框 → BuildingParams)
- ❌ 额度 / 登录 / 历史记录
- ❌ 完整平面文法(房间拓扑 / 尺寸标注)

## 对既有约束的遵守

- 纯 Python 程序化绘图(Pillow),本机 0 GPU 可行
- uv 管理依赖;ruff lint + pytest 全绿才算任务完成
- 双语文案走 i18n,不硬编码散落中文字符串
- API 密钥依旧从环境变量读取(本阶段不新增密钥)
