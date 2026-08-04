# 阶段 2:生成服务 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接通出图闭环——输入建筑参数,本地程序化生成效果图(3/4 透视立面)与平面示意,静态文件交付,前端表单下方展示。

**Architecture:** 新增 `generation/generators/` 包:`Generator` 协议接口定义契约,`SimulatorGenerator` 用 Pillow 本地确定性绘图(立面文法 → 透视投影 → 平面示意),渲染在 `asyncio.to_thread` 中执行。API 层注入生成器,产物落盘 `cache_dir/{scheme_id}/`,由 `StaticFiles` 提供访问,前端 `ParamForm` 提交后展示两张图。

**Tech Stack:** Python 3.11、Pillow、FastAPI、pydantic v2、pytest、ruff;前端 React + Vite + TypeScript。

## Global Constraints

- Python >= 3.11(本机 3.11.15),包管理用 `uv`,不用 pip 直接装
- 前端 React + Vite + TypeScript;双语文案放 `frontend/src/i18n/{en,zh}.json`,硬编码散落中文字符串视为缺陷
- API 密钥一律从环境变量读取,代码中不得出现明文密钥
- ruff lint 与 format 必须通过;pytest 全绿才算任务完成
- 提交信息用 `feat:` / `fix:` / `docs:` 前缀
- 所有生成产物落盘 `cache_dir`(默认 `.cache/archgen`),已被 `.gitignore` 覆盖不入库
- 本阶段不接 Replicate/Fal 真 API、不接 NL 解析、不做额度/登录/历史(见规格"明确排除")

---

### Task 1: Pillow 依赖与生成器抽象(base.py)

**Files:**
- Modify: `pyproject.toml`(dependencies 加 `pillow`)
- Create: `generation/generators/__init__.py`
- Create: `generation/generators/base.py`
- Create: `tests/test_generator_base.py`

**Interfaces:**
- Produces:
  - `class ImageRef(BaseModel)`:`kind: Literal["facade", "floorplan"]`、`url: str`
  - `class GenerationArtifact(BaseModel)`:`scheme_id: str`、`images: list[ImageRef]`
  - `class Generator(Protocol)`: `async def generate(self, params: BuildingParams, scheme_id: str, out_dir: Path, lang: Literal["en", "zh"] = "zh") -> GenerationArtifact`
  - `from generation.generators import Generator, GenerationArtifact, ImageRef, SimulatorGenerator`

- [ ] **Step 1: 添加 Pillow 依赖**

```bash
uv add pillow
```

Expected: `pillow` 进入 `pyproject.toml` dependencies 与 `uv.lock`。

- [ ] **Step 2: 写失败的测试**

```python
# tests/test_generator_base.py
from typing import AsyncGenerator

import pytest

from generation.generators.base import Generator, GenerationArtifact, ImageRef
from generation.params.model import BuildingParams


def test_image_ref_model():
    ref = ImageRef(kind="facade", url="/images/abc/facade.png")
    assert ref.kind == "facade"
    assert ref.url.endswith("facade.png")


def test_generation_artifact_model():
    art = GenerationArtifact(
        scheme_id="abc",
        images=[ImageRef(kind="facade", url="/images/abc/facade.png")],
    )
    assert art.scheme_id == "abc"
    assert len(art.images) == 1


class DummyGenerator:
    """实现 Generator 协议的桩,仅用于协议可用性检查。"""

    async def generate(self, params, scheme_id, out_dir, lang="zh"):
        return GenerationArtifact(scheme_id=scheme_id, images=[])


@pytest.mark.asyncio
async def test_generator_protocol_dummy():
    gen: Generator = DummyGenerator()
    params = BuildingParams(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    art = await gen.generate(params, "abc", __import__("pathlib").Path("."), "zh")
    assert isinstance(art, GenerationArtifact)
    assert art.scheme_id == "abc"
```

- [ ] **Step 3: 运行测试验证失败**

Run: `uv run pytest tests/test_generator_base.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators'`

- [ ] **Step 4: 实现 base.py 与包初始化**

```python
# generation/generators/base.py
from typing import Literal, Protocol

from pydantic import BaseModel

from generation.params.model import BuildingParams


class ImageRef(BaseModel):
    kind: Literal["facade", "floorplan"]
    url: str


class GenerationArtifact(BaseModel):
    scheme_id: str
    images: list[ImageRef]


class Generator(Protocol):
    """生成器契约——模拟器与未来 API/真实模型共用,网页层零改动。"""

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: object,
        lang: Literal["en", "zh"] = "zh",
    ) -> GenerationArtifact: ...
```

```python
# generation/generators/__init__.py
from generation.generators.base import (
    GenerationArtifact,
    Generator,
    ImageRef,
)

__all__ = ["GenerationArtifact", "Generator", "ImageRef"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `uv run pytest tests/test_generator_base.py -v`
Expected: 3 个测试全部 PASS

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml uv.lock generation/generators/ tests/test_generator_base.py
git commit -m "feat: 添加生成器抽象(Generator 协议 + GenerationArtifact)"
```

---

### Task 2: 立面文法(facade.py)

**Files:**
- Create: `generation/generators/simulator/__init__.py`
- Create: `generation/generators/simulator/facade.py`
- Create: `tests/test_facade.py`

**Interfaces:**
- Consumes: `BuildingParams`(已有)
- Produces:
  - `class FacadeSpec(BaseModel)`:`width_px: int`、`height_px: int`、`floors: int`、`windows: list[WindowRect]`、`roof: Literal["flat", "pitched", "hipped"]`、`palette: MaterialPalette`
  - `class WindowRect(BaseModel)`:`x: int`、`y: int`、`w: int`、`h: int`、`cross: bool`(是否画十字窗棂)
  - `class MaterialPalette(BaseModel)`:`main: str`、`accent: str`、`trim: str`(十六进制颜色,如 `"#f5f5f0"`)
  - `def build_facade_spec(params: BuildingParams, width_px: int = 640, height_px: int = 480) -> FacadeSpec`
  - `MATERIAL_COLORS: dict[str, MaterialPalette]`(glass/stone/brick/wood 四个键)

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_facade.py
import pytest

from generation.generators.simulator.facade import (
    MATERIAL_COLORS,
    build_facade_spec,
)
from generation.params.model import BuildingParams


def _params(**overrides):
    base = dict(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    base.update(overrides)
    return BuildingParams(**base)


def test_build_facade_spec_basic():
    spec = build_facade_spec(_params(floors=3))
    assert spec.width_px == 640
    assert spec.height_px == 480
    assert spec.floors == 3
    assert len(spec.windows) > 0
    for w in spec.windows:
        assert 0 <= w.x < spec.width_px
        assert 0 <= w.y < spec.height_px
        assert w.w > 0 and w.h > 0


def test_build_facade_spec_window_count_scales_with_floors():
    spec1 = build_facade_spec(_params(floors=1))
    spec3 = build_facade_spec(_params(floors=3))
    # 每层都有窗;总窗数随层数单调不减
    assert len(spec3.windows) >= len(spec1.windows) + 1


def test_roof_style_variation():
    flat = build_facade_spec(_params(roof="flat"))
    pitched = build_facade_spec(_params(roof="pitched"))
    assert flat.roof == "flat"
    assert pitched.roof == "pitched"


def test_material_palette_keys():
    assert set(MATERIAL_COLORS.keys()) == {"glass", "stone", "brick", "wood"}
    for pal in MATERIAL_COLORS.values():
        assert pal.main.startswith("#")
        assert pal.accent.startswith("#")
        assert pal.trim.startswith("#")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_facade.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators.simulator'`

- [ ] **Step 3: 实现 facade.py 与包初始化**

```python
# generation/generators/simulator/__init__.py
"""本地模拟器生成器——护城河:参数 → 程序化线稿。"""
```

```python
# generation/generators/simulator/facade.py
from pydantic import BaseModel

from generation.params.model import BuildingParams

FLOOR_HEIGHT_M = 3.2  # 与 params.model 一致
MAX_WIDTH_PX = 640
MAX_HEIGHT_PX = 480


class WindowRect(BaseModel):
    x: int
    y: int
    w: int
    h: int
    cross: bool = True


class MaterialPalette(BaseModel):
    main: str
    accent: str
    trim: str


MATERIAL_COLORS: dict[str, MaterialPalette] = {
    "glass": MaterialPalette(main="#b8d8e8", accent="#e8f4f8", trim="#5b7f95"),
    "stone": MaterialPalette(main="#d9d2c0", accent="#efe9d8", trim="#8a8270"),
    "brick": MaterialPalette(main="#c0693f", accent="#e5d8c8", trim="#7a4a2b"),
    "wood": MaterialPalette(main="#b5936b", accent="#dcc9a8", trim="#6e5637"),
}


class FacadeSpec(BaseModel):
    width_px: int
    height_px: int
    floors: int
    windows: list[WindowRect]
    roof: str
    palette: MaterialPalette


def _window_cols(width_px: int) -> int:
    # 按面宽推导窗列数:6-10m 两列,11-20m 三列
    return 2 if width_px < 0.5 * MAX_WIDTH_PX else 3


def _window_row(floor_idx: int, floors: int, window_h: int) -> int:
    # 每层窗在层内垂直居中,层间留缝
    return 40 + floor_idx * (window_h + 60) + 10


def _window_rows(floors: int, height_px: int, margin: int, scale: float) -> list[int]:
    """按层数在画布高度内均分楼层,返回每层窗的 y 坐标(层内垂直居中)。

    保证任意 floors(1-6)下窗口都不超出画布。
    """
    avail_h = height_px - 2 * margin
    floor_h = avail_h // floors
    window_h = max(20, floor_h - 24)
    return [margin + f * floor_h + (floor_h - window_h) // 2 for f in range(floors)]


def build_facade_spec(params: BuildingParams, width_px: int = 640, height_px: int = 480) -> FacadeSpec:
    scale = width_px / MAX_WIDTH_PX  # 相对默认面宽的比例
    palette = MATERIAL_COLORS[params.materials[0]]
    floors = params.floors
    margin = int(40 * scale)
    window_w = int(90 * scale)
    cols = _window_cols(width_px)
    gap = (width_px - 2 * margin - cols * window_w) // (cols - 1) if cols > 1 else 0

    ys = _window_rows(floors, height_px, margin, scale)
    window_h = (ys[1] - ys[0] - 10) if floors > 1 else max(20, (height_px - 2 * margin) - 60)

    windows: list[WindowRect] = []
    for floor_idx, y in enumerate(ys):
        for c in range(cols):
            x = margin + c * (window_w + gap)
            windows.append(WindowRect(x=x, y=y, w=window_w, h=window_h))

    return FacadeSpec(
        width_px=width_px,
        height_px=height_px,
        floors=floors,
        windows=windows,
        roof=params.roof,
        palette=palette,
    )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_facade.py -v`
Expected: 4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add generation/generators/simulator/ tests/test_facade.py
git commit -m "feat: 添加立面文法(参数→FacadeSpec 线框)"
```

---

### Task 3: 3/4 透视投影(perspective.py)

**Files:**
- Create: `generation/generators/simulator/perspective.py`
- Create: `tests/test_perspective.py`

**Interfaces:**
- Consumes: `FacadeSpec`(Task 2)
- Produces:
  - `class Point(BaseModel)`:`x: float`、`y: float`
  - `def project_iso(x: float, y: float, depth: float, depth_scale: float = 0.5) -> Point` — 将正立面点 (x, y) 叠加深度 depth 投影为 3/4 等轴视角点
  - `def project_rect(rect: tuple[float, float, float, float], depth: float) -> tuple[Point, Point, Point, Point]` — 将矩形 (x, y, w, h) 投影为四角点(逆时针,含深度偏移)

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_perspective.py
import pytest

from generation.generators.simulator.perspective import (
    Point,
    project_iso,
    project_rect,
)


def test_project_iso_zero_depth_identity():
    p = project_iso(100.0, 200.0, depth=0.0)
    assert p.x == pytest.approx(100.0)
    assert p.y == pytest.approx(200.0)


def test_project_iso_positive_depth_offsets_x_and_y():
    p = project_iso(100.0, 200.0, depth=50.0, depth_scale=0.5)
    # 深度向右、向下偏移,形成等轴感
    assert p.x > 100.0
    assert p.y > 200.0


def test_project_rect_four_corners():
    pts = project_rect((100, 200, 40, 60), depth=0.0)
    assert len(pts) == 4
    # 逆时针:左上、右上、右下、左下
    assert pts[0].x == 100 and pts[0].y == 200
    assert pts[1].x == 140 and pts[1].y == 200
    assert pts[2].x == 140 and pts[2].y == 260
    assert pts[3].x == 100 and pts[3].y == 260
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_perspective.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators.simulator.perspective'`

- [ ] **Step 3: 实现 perspective.py**

```python
# generation/generators/simulator/perspective.py
from pydantic import BaseModel


class Point(BaseModel):
    x: float
    y: float


def project_iso(x: float, y: float, depth: float, depth_scale: float = 0.5) -> Point:
    """等轴投影:正立面点叠加深度,向右下方偏移形成 3/4 视角。"""
    return Point(x=x + depth * depth_scale, y=y + depth * depth_scale)


def project_rect(rect: tuple[float, float, float, float], depth: float) -> tuple[Point, Point, Point, Point]:
    """将正立面矩形 (x, y, w, h) 投影为四角点(逆时针)。"""
    x, y, w, h = rect
    return (
        project_iso(x, y, depth),
        project_iso(x + w, y, depth),
        project_iso(x + w, y + h, depth),
        project_iso(x, y + h, depth),
    )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_perspective.py -v`
Expected: 3 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add generation/generators/simulator/perspective.py tests/test_perspective.py
git commit -m "feat: 添加 3/4 等轴透视投影"
```

---

### Task 4: 平面示意(floorplan.py)

**Files:**
- Create: `generation/generators/simulator/floorplan.py`
- Create: `tests/test_floorplan.py`

**Interfaces:**
- Consumes: `BuildingParams`(已有)
- Produces:
  - `class RoomLabel(BaseModel)`:`text: str`、`x: int`、`y: int`、`w: int`、`h: int`
  - `class FloorplanSpec(BaseModel)`:`width_px: int`、`height_px: int`、`outer: tuple[int, int, int, int]`(外墙矩形 x,y,w,h)、`rooms: list[RoomLabel]`
  - `ROOM_NAMES_ZH: list[str]` = `["厨房", "卧室", "客厅", "卫生间"]`
  - `ROOM_NAMES_EN: list[str]` = `["Kitchen", "Bedroom", "Living", "Bath"]`
  - `def build_floorplan_spec(params: BuildingParams, lang: str = "zh", width_px: int = 480, height_px: int = 360) -> FloorplanSpec`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_floorplan.py
import pytest

from generation.generators.simulator.floorplan import (
    ROOM_NAMES_EN,
    ROOM_NAMES_ZH,
    build_floorplan_spec,
)
from generation.params.model import BuildingParams


def _params(**overrides):
    base = dict(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    base.update(overrides)
    return BuildingParams(**base)


def test_floorplan_outer_rect_within_canvas():
    spec = build_floorplan_spec(_params())
    x, y, w, h = spec.outer
    assert x >= 0 and y >= 0
    assert x + w <= spec.width_px
    assert y + h <= spec.height_px
    assert w > 0 and h > 0


def test_floorplan_rooms_zh():
    spec = build_floorplan_spec(_params(), lang="zh")
    texts = [r.text for r in spec.rooms]
    assert any(t in ROOM_NAMES_ZH for t in texts)


def test_floorplan_rooms_en():
    spec = build_floorplan_spec(_params(), lang="en")
    texts = [r.text for r in spec.rooms]
    assert any(t in ROOM_NAMES_EN for t in texts)


def test_floorplan_room_count_scales_with_width():
    spec_small = build_floorplan_spec(_params(width_m=6.0))
    spec_large = build_floorplan_spec(_params(width_m=20.0))
    assert len(spec_large.rooms) >= len(spec_small.rooms)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_floorplan.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators.simulator.floorplan'`

- [ ] **Step 3: 实现 floorplan.py**

```python
# generation/generators/simulator/floorplan.py
from pydantic import BaseModel

from generation.params.model import BuildingParams

ROOM_NAMES_ZH = ["厨房", "卧室", "客厅", "卫生间"]
ROOM_NAMES_EN = ["Kitchen", "Bedroom", "Living", "Bath"]


class RoomLabel(BaseModel):
    text: str
    x: int
    y: int
    w: int
    h: int


class FloorplanSpec(BaseModel):
    width_px: int
    height_px: int
    outer: tuple[int, int, int, int]  # (x, y, w, h) 外墙矩形
    rooms: list[RoomLabel]


def build_floorplan_spec(
    params: BuildingParams,
    lang: str = "zh",
    width_px: int = 480,
    height_px: int = 360,
) -> FloorplanSpec:
    names = ROOM_NAMES_ZH if lang == "zh" else ROOM_NAMES_EN
    margin = 30
    avail_w = width_px - 2 * margin
    avail_h = height_px - 2 * margin
    # 按宽深比缩放外墙矩形
    ratio = params.depth_m / params.width_m if params.width_m else 0.8
    if ratio > avail_h / avail_w:
        h = avail_h
        w = int(h * params.width_m / params.depth_m)
    else:
        w = avail_w
        h = int(w * ratio)
    outer = (margin, margin, w, h)

    # 按宽度切 2-3 列,按层数切 2 行,形成房间网格
    cols = 2 if params.width_m < 12 else 3
    rows = 2
    cell_w = w // cols
    cell_h = h // rows
    rooms: list[RoomLabel] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            name = names[idx % len(names)]
            rooms.append(
                RoomLabel(
                    text=name,
                    x=margin + c * cell_w,
                    y=margin + r * cell_h,
                    w=cell_w,
                    h=cell_h,
                )
            )
            idx += 1
    return FloorplanSpec(
        width_px=width_px,
        height_px=height_px,
        outer=outer,
        rooms=rooms,
    )
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_floorplan.py -v`
Expected: 4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add generation/generators/simulator/floorplan.py tests/test_floorplan.py
git commit -m "feat: 添加平面示意(外墙+内墙网格+房间标签)"
```

---

### Task 5: 模拟器渲染器(renderer.py)

**Files:**
- Create: `generation/generators/simulator/renderer.py`
- Create: `tests/test_renderer.py`

**Interfaces:**
- Consumes: `FacadeSpec`(Task 2)、`project_iso`/`project_rect`(Task 3)、`FloorplanSpec`(Task 4)
- Produces:
  - `async def render_scheme(params: BuildingParams, scheme_id: str, out_dir: object, lang: Literal["en", "zh"] = "zh") -> GenerationArtifact` — 在 `asyncio.to_thread` 中同步绘制 facade.png 与 floorplan.png 到 `out_dir`,返回 artifact(URL 形如 `/images/{scheme_id}/facade.png`)
  - 同步辅助:`def _render_facade_png(spec: FacadeSpec, out_path: object) -> None`、`def _render_floorplan_png(spec: FloorplanSpec, out_path: object) -> None`(内部使用 Pillow)

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_renderer.py
import asyncio
from pathlib import Path

import pytest

from generation.generators.base import GenerationArtifact
from generation.generators.simulator import renderer
from generation.params.model import BuildingParams


def _params(**overrides):
    base = dict(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    base.update(overrides)
    return BuildingParams(**base)


def test_render_facade_png_creates_file(tmp_path: Path):
    from generation.generators.simulator.facade import build_facade_spec

    spec = build_facade_spec(_params())
    out = tmp_path / "facade.png"
    renderer._render_facade_png(spec, out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_render_floorplan_png_creates_file(tmp_path: Path):
    from generation.generators.simulator.floorplan import build_floorplan_spec

    spec = build_floorplan_spec(_params())
    out = tmp_path / "floorplan.png"
    renderer._render_floorplan_png(spec, out)
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.asyncio
async def test_render_scheme_returns_artifact(tmp_path: Path):
    art = await renderer.render_scheme(_params(), "abc123", tmp_path, "zh")
    assert isinstance(art, GenerationArtifact)
    assert art.scheme_id == "abc123"
    assert len(art.images) == 2
    kinds = {img.kind for img in art.images}
    assert kinds == {"facade", "floorplan"}
    for img in art.images:
        assert img.url.startswith("/images/abc123/")
        path = tmp_path / img.url.rsplit("/", 1)[-1]
        assert path.exists()


@pytest.mark.asyncio
async def test_render_scheme_respects_lang(tmp_path: Path):
    art_zh = await renderer.render_scheme(_params(), "a", tmp_path, "zh")
    art_en = await renderer.render_scheme(_params(), "b", tmp_path, "en")
    assert len(art_zh.images) == 2
    assert len(art_en.images) == 2
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_renderer.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'generation.generators.simulator.renderer'`

- [ ] **Step 3: 实现 renderer.py**

```python
# generation/generators/simulator/renderer.py
import asyncio
from typing import Literal

from PIL import Image, ImageDraw

from generation.generators.base import GenerationArtifact, ImageRef
from generation.generators.simulator.facade import FacadeSpec, build_facade_spec
from generation.generators.simulator.floorplan import FloorplanSpec, build_floorplan_spec
from generation.generators.simulator.perspective import project_iso, project_rect
from generation.params.model import BuildingParams

FACADE_FILE = "facade.png"
FLOORPLAN_FILE = "floorplan.png"
FACADE_OUTPUT_PX = (640, 480)
FLOORPLAN_OUTPUT_PX = (480, 360)


def _draw_facade_rect(draw: ImageDraw.ImageDraw, spec: FacadeSpec) -> None:
    """在画布上绘制正立面:体量轮廓、分层线、开窗网格。"""
    x0, y0 = 30, 30
    x1 = spec.width_px - 30
    y1 = spec.height_px - 30
    floor_h = (y1 - y0) // spec.floors
    draw.rectangle([x0, y0, x1, y1], fill=spec.palette.main, outline=spec.palette.trim, width=3)
    for f in range(1, spec.floors):
        fy = y0 + f * floor_h
        draw.line([x0, fy, x1, fy], fill=spec.palette.trim, width=2)
    for w in spec.windows:
        draw.rectangle([w.x + x0, w.y + y0, w.x + w.w + x0, w.y + w.h + y0],
                       fill=spec.palette.accent, outline=spec.palette.trim, width=2)
        if w.cross:
            cx = w.x + x0 + w.w // 2
            cy = w.y + y0 + w.h // 2
            draw.line([cx, w.y + y0, cx, w.y + w.h + y0], fill=spec.palette.trim, width=1)
            draw.line([w.x + x0, cy, w.x + w.w + x0, cy], fill=spec.palette.trim, width=1)


def _draw_facade_perspective(draw: ImageDraw.ImageDraw, spec: FacadeSpec) -> None:
    """绘制 3/4 透视:正立面投影 + 侧壁与顶面的体量感。"""
    x0, y0 = 30, 30
    x1 = spec.width_px - 30
    y1 = spec.height_px - 30
    depth = 50  # 深度偏移 50*0.5=25px,保证顶面/侧壁不出画布(640×480)
    # 正立面(已投影,深度 0 时与立面一致)
    front = project_rect((x0, y0, x1 - x0, y1 - y0), depth=0)
    # 侧壁:右边界向纵深偏移,形成顶面/侧壁
    back = project_rect((x0, y0, x1 - x0, y1 - y0), depth=depth)
    pts_front = [(p.x, p.y) for p in front]
    draw.polygon(pts_front, fill=spec.palette.main, outline=spec.palette.trim)
    # 顶面:正立面顶边 → 侧壁顶边
    draw.polygon(
        [(front[0].x, front[0].y), (front[1].x, front[1].y),
         (back[1].x, back[1].y), (back[0].x, back[0].y)],
        fill=spec.palette.accent, outline=spec.palette.trim,
    )
    # 侧壁(右):正立面右边 → 侧壁右边
    draw.polygon(
        [(front[1].x, front[1].y), (front[2].x, front[2].y),
         (back[2].x, back[2].y), (back[1].x, back[1].y)],
        fill=spec.palette.main, outline=spec.palette.trim,
    )
    # 窗在正立面(投影深度 0)
    for w in spec.windows:
        wp = project_rect((w.x + x0, w.y + y0, w.w, w.h), depth=0)
        draw.polygon([(p.x, p.y) for p in wp],
                     fill=spec.palette.accent, outline=spec.palette.trim, width=2)
        if w.cross:
            cx = w.x + x0 + w.w // 2
            cy = w.y + y0 + w.h // 2
            draw.line([cx, w.y + y0, cx, w.y + w.h + y0], fill=spec.palette.trim, width=1)
            draw.line([w.x + x0, cy, w.x + w.w + x0, cy], fill=spec.palette.trim, width=1)


def _render_facade_png(spec: FacadeSpec, out_path: object) -> None:
    img = Image.new("RGB", FACADE_OUTPUT_PX, "#ffffff")
    draw = ImageDraw.Draw(img)
    _draw_facade_perspective(draw, spec)
    img.save(str(out_path))


def _render_floorplan_png(spec: FloorplanSpec, out_path: object) -> None:
    img = Image.new("RGB", FLOORPLAN_OUTPUT_PX, "#ffffff")
    draw = ImageDraw.Draw(img)
    x, y, w, h = spec.outer
    draw.rectangle([x, y, x + w, y + h], outline="#333333", width=3)
    for room in spec.rooms:
        draw.rectangle(
            [room.x, room.y, room.x + room.w, room.y + room.h],
            outline="#999999", width=1,
        )
        draw.text((room.x + 8, room.y + 8), room.text, fill="#333333")
    img.save(str(out_path))


def _render_sync(params: BuildingParams, scheme_id: str, out_dir: object, lang: str) -> GenerationArtifact:
    import pathlib

    out = pathlib.Path(out_dir)
    facade = build_facade_spec(params)
    _render_facade_png(facade, out / FACADE_FILE)
    floorplan = build_floorplan_spec(params, lang=lang)
    _render_floorplan_png(floorplan, out / FLOORPLAN_FILE)
    return GenerationArtifact(
        scheme_id=scheme_id,
        images=[
            ImageRef(kind="facade", url=f"/images/{scheme_id}/{FACADE_FILE}"),
            ImageRef(kind="floorplan", url=f"/images/{scheme_id}/{FLOORPLAN_FILE}"),
        ],
    )


async def render_scheme(
    params: BuildingParams,
    scheme_id: str,
    out_dir: object,
    lang: Literal["en", "zh"] = "zh",
) -> GenerationArtifact:
    """模拟器渲染入口——同步绘制在线程池,避免阻塞事件循环。"""
    return await asyncio.to_thread(_render_sync, params, scheme_id, out_dir, lang)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_renderer.py -v`
Expected: 4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add generation/generators/simulator/renderer.py tests/test_renderer.py
git commit -m "feat: 添加模拟器渲染器(线稿→透视→平面→PNG 落盘)"
```

---

### Task 6: 生成器组装与编排(simulator/__init__.py)

**Files:**
- Modify: `generation/generators/simulator/__init__.py`
- Create: `generation/generators/__init__.py`(补充导出)
- Create: `tests/test_simulator_generator.py`

**Interfaces:**
- Consumes: `render_scheme`(Task 5)、`Generator` 协议(Task 1)
- Produces:
  - `class SimulatorGenerator:` 实现 `Generator` 协议:`async def generate(self, params, scheme_id, out_dir, lang="zh") -> GenerationArtifact`,直接代理 `render_scheme`
  - `from generation.generators import SimulatorGenerator`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_simulator_generator.py
from pathlib import Path

import pytest

from generation.generators import SimulatorGenerator
from generation.params.model import BuildingParams


def _params(**overrides):
    base = dict(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    base.update(overrides)
    return BuildingParams(**base)


@pytest.mark.asyncio
async def test_simulator_generator_generate(tmp_path: Path):
    gen = SimulatorGenerator()
    art = await gen.generate(_params(), "sid-1", tmp_path, "zh")
    assert art.scheme_id == "sid-1"
    assert len(art.images) == 2
    for img in art.images:
        assert (tmp_path / img.url.rsplit("/", 1)[-1]).exists()


@pytest.mark.asyncio
async def test_simulator_generator_default_lang(tmp_path: Path):
    gen = SimulatorGenerator()
    art = await gen.generate(_params(), "sid-2", tmp_path)
    assert len(art.images) == 2
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_simulator_generator.py -v`
Expected: FAIL,`ImportError: cannot import name 'SimulatorGenerator' from 'generation.generators'`

- [ ] **Step 3: 实现 SimulatorGenerator**

```python
# generation/generators/simulator/__init__.py
"""本地模拟器生成器——护城河:参数 → 程序化线稿。"""

from generation.generators.base import GenerationArtifact
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams


class SimulatorGenerator:
    """本地模拟器:参数 → 透视立面 + 平面示意 PNG。"""

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: object,
        lang: str = "zh",
    ) -> GenerationArtifact:
        return await render_scheme(params, scheme_id, out_dir, lang)


__all__ = ["SimulatorGenerator"]
```

```python
# generation/generators/__init__.py
from generation.generators.base import (
    GenerationArtifact,
    Generator,
    ImageRef,
)
from generation.generators.simulator import SimulatorGenerator

__all__ = [
    "GenerationArtifact",
    "Generator",
    "ImageRef",
    "SimulatorGenerator",
]
```

- [ ] **Step 4: 运行测试验证通过**

Run: `uv run pytest tests/test_simulator_generator.py -v`
Expected: 2 个测试全部 PASS

- [ ] **Step 5: 运行全量测试与 lint**

Run:
```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```
Expected: 全部 PASS,ruff 无报错。

- [ ] **Step 6: 提交**

```bash
git add generation/generators/ tests/test_simulator_generator.py
git commit -m "feat: 组装 SimulatorGenerator(实现 Generator 协议)"
```

---

### Task 7: API 接入生成器 + 静态文件服务

**Files:**
- Modify: `backend/app/main.py`(挂载 StaticFiles)
- Modify: `backend/app/schemas/generate.py`(确认 images 类型)
- Modify: `backend/app/api/generate.py`(注入并调用 Generator)
- Modify: `tests/test_api.py`(更新 generate 断言)

**Interfaces:**
- Consumes: `SimulatorGenerator`(Task 6)、`Settings.cache_dir`(已有)
- Produces:
  - `GET /images/{scheme_id}/{file}` → PNG(由 `StaticFiles(directory=cache_dir)` 提供)
  - `POST /api/v1/generate` 现返回非空 `images: [url]`(效果图 + 平面图 URL)

- [ ] **Step 1: 更新 API 测试**

```python
# tests/test_api.py 中修改 test_generate_skeleton 为:
def test_generate_skeleton(tmp_path):
    from backend.app.core.config import Settings
    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="replicate",
        max_free_quota=5,
        cache_dir=str(tmp_path),
    )
    client = TestClient(create_app(settings))
    resp = client.post(
        "/api/v1/generate",
        json={
            "params": {
                "style": "modern",
                "floors": 3,
                "width_m": 10.0,
                "depth_m": 8.0,
                "materials": ["glass"],
                "roof": "flat",
                "environment": "suburb",
            },
            "lang": "zh",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scheme_id"]
    assert len(body["images"]) == 2
    assert "设计" in body["description"]  # 空 key → 占位文案分支
    # 静态文件可访问
    for url in body["images"]:
        img_resp = client.get(url)
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"] == "image/png"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `uv run pytest tests/test_api.py::test_generate_skeleton -v`
Expected: FAIL,`images == []`(仍返回空,静态文件也不存在)

- [ ] **Step 3: 修改 schemas/generate.py(确认 images 为 URL 列表)**

```python
# backend/app/schemas/generate.py
class GenerationResponse(BaseModel):
    scheme_id: str
    description: str
    images: list[str] = []  # 图片 URL 列表(静态文件路径)
```

- [ ] **Step 4: 修改 main.py 挂载静态文件**

```python
# backend/app/main.py
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.generate import router as generate_router
from backend.app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="ArchGen API", version="0.1.0")
    app.state.settings = settings or get_settings()

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(generate_router, prefix="/api/v1")

    import pathlib

    cache_dir = pathlib.Path(app.state.settings.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(cache_dir)), name="images")
    return app


def run() -> None:
    """uvicorn 入口(供 `archgen-api` 脚本使用)。"""
    uvicorn.run("backend.app.main:create_app", factory=True, host="0.0.0.0", port=8000)
```

- [ ] **Step 5: 修改 generate.py 接入生成器**

```python
# backend/app/api/generate.py
import pathlib
import uuid

from fastapi import APIRouter, Request

from backend.app.core.config import Settings
from backend.app.schemas.generate import GenerateRequest, GenerationResponse
from generation.generators import SimulatorGenerator
from generation.llm.deepseek_client import DeepSeekClient

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: GenerateRequest, request: Request) -> GenerationResponse:
    """生成:校验参数 + 本地模拟器出图(效果图 + 平面图)。"""
    settings: Settings = request.app.state.settings  # 从 app.state 读取(支持测试注入)
    scheme_id = str(uuid.uuid4())
    if not settings.deepseek_api_key:
        description = (
            "测试占位文案:建筑设计描述" if req.lang == "zh" else "Placeholder scheme description"
        )
    else:
        client = DeepSeekClient(settings.deepseek_api_key, settings.deepseek_base_url)
        description = await client.describe_scheme(req.params, req.lang)

    out_dir = pathlib.Path(settings.cache_dir) / scheme_id
    out_dir.mkdir(parents=True, exist_ok=True)
    generator = SimulatorGenerator()
    artifact = await generator.generate(req.params, scheme_id, out_dir, req.lang)
    return GenerationResponse(
        scheme_id=scheme_id,
        description=description,
        images=[img.url for img in artifact.images],
    )
```

- [ ] **Step 6: 运行测试验证通过**

Run: `uv run pytest tests/test_api.py -v`
Expected: 3 个测试全部 PASS(test_health、test_generate_skeleton、test_generate_invalid_params)

- [ ] **Step 7: 运行 lint 并提交**

Run: `uv run ruff check . && uv run ruff format .`
Expected: 无报错,格式化完成。

```bash
git add backend/ tests/test_api.py
git commit -m "feat: API 接入模拟器生成器并挂载静态图片服务"
```

---

### Task 8: 前端展示生成结果

**Files:**
- Modify: `frontend/src/api/client.ts`(确认接口,补充 `lang` 参数)
- Modify: `frontend/src/components/ParamForm/ParamForm.tsx`(提交后调 API,展示图片)
- Modify: `frontend/src/i18n/{zh,en}.json`(补充结果相关文案)
- Modify: `frontend/src/i18n/index.ts`(加载 lang 状态,默认 zh)

**Interfaces:**
- Consumes: `generateScheme(params, lang)`(已有)、`GenerateResponse`(已有)
- Produces: 表单下方并排展示效果图 + 平面图 `<img>`

- [ ] **Step 1: 确认 client.ts 已有 lang 参数**

`frontend/src/api/client.ts` 已有 `generateScheme(params, lang = "zh")`。确认不改(接口已满足)。

- [ ] **Step 2: 补充 i18n 文案**

```json
// frontend/src/i18n/zh.json 追加:
{ "app_title": "ArchGen 建筑方案生成", "style": "风格", "floors": "层数", "width": "面宽(m)", "depth": "进深(m)", "material": "材质", "generate": "生成方案",
  "facade_label": "效果图", "floorplan_label": "平面图", "generating": "生成中…", "error": "生成失败,请重试" }
```

```json
// frontend/src/i18n/en.json 追加:
{ "app_title": "ArchGen Building Generator", "style": "Style", "floors": "Floors", "width": "Width (m)", "depth": "Depth (m)", "material": "Material", "generate": "Generate",
  "facade_label": "Facade", "floorplan_label": "Floorplan", "generating": "Generating…", "error": "Generation failed, try again" }
```

- [ ] **Step 3: 更新 index.ts(暴露生成文案)**

```ts
// frontend/src/i18n/index.ts
import zh from "./zh.json";

export const messages = zh;
```

保持现状(当前只加载 zh;文案键已含新增)。

- [ ] **Step 4: 更新 ParamForm 展示结果**

```tsx
// frontend/src/components/ParamForm/ParamForm.tsx
import { useState } from "react";
import { generateScheme } from "../../api/client";
import { messages } from "../../i18n";

const STYLES = ["modern", "neoclassic", "european", "nordic"];
const MATERIALS = ["glass", "stone", "brick", "wood"];
const ROOFS = ["flat", "pitched", "hipped"];
const ENVS = ["urban", "suburb", "rural", "seaside"];

interface ResultImages {
  facade?: string;
  floorplan?: string;
}

export default function ParamForm() {
  const [style, setStyle] = useState("modern");
  const [floors, setFloors] = useState(3);
  const [widthM, setWidthM] = useState(10);
  const [depthM, setDepthM] = useState(8);
  const [material, setMaterial] = useState("glass");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [images, setImages] = useState<ResultImages>({});

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await generateScheme(
        {
          style,
          floors,
          width_m: widthM,
          depth_m: depthM,
          materials: [material],
          roof: "flat",
          environment: "suburb",
        },
        "zh"
      );
      const facade = res.images.find((u) => u.includes("facade"));
      const floorplan = res.images.find((u) => u.includes("floorplan"));
      setImages({ facade, floorplan });
    } catch (err) {
      setError(messages.error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: "1rem" }}>
        {/* 原有表单字段保持不变 */}
        <button type="submit" disabled={loading}>
          {loading ? messages.generating : messages.generate}
        </button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {(images.facade || images.floorplan) && (
        <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
          {images.facade && (
            <figure>
              <figcaption>{messages.facade_label}</figcaption>
              <img src={images.facade} alt={messages.facade_label} style={{ width: 320 }} />
            </figure>
          )}
          {images.floorplan && (
            <figure>
              <figcaption>{messages.floorplan_label}</figcaption>
              <img src={images.floorplan} alt={messages.floorplan_label} style={{ width: 240 }} />
            </figure>
          )}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 5: 运行前端 build 验证**

Run: `cd frontend && npm run build`
Expected: TypeScript 编译通过,无类型错误。

- [ ] **Step 6: 提交**

```bash
git add frontend/
git commit -m "feat: 前端表单下方展示生成效果图与平面图"
```

---

### Task 9: 端到端冒烟验证(阶段 2 完成标准)

**Files:**
- Modify: `docs/gallery/smoke-test.md`(追加阶段 2 记录)

**Interfaces:**
- Consumes: Task 1-8 全部产物

- [ ] **Step 1: 运行全量测试与 lint**

Run:
```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```
Expected: 全部 PASS,ruff 无报错。

- [ ] **Step 2: 启动后端并验证生成**

Run(终端 A): `uv run archgen-api`
Expected: uvicorn 在 8000 端口启动。

Run(终端 B):
```bash
curl -s -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"params":{"style":"modern","floors":3,"width_m":10,"depth_m":8,"materials":["glass"],"roof":"flat","environment":"suburb"},"lang":"zh"}'
```
Expected: 返回 JSON,`images` 含 2 个 `/images/{scheme_id}/...` URL。

```bash
# 取返回的 facade URL 验证可访问
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/images/{scheme_id}/facade.png
```
Expected: `200`

- [ ] **Step 3: 启动前端并验证页面展示**

Run(终端 C): `cd frontend && npm run dev`
Expected: Vite 在 5173 端口启动。

浏览器访问 `http://localhost:5173`,填参数点「生成方案」,Expected: 表单下方展示效果图与平面图两张 PNG。

- [ ] **Step 4: 记录冒烟结果**

```bash
echo "- 阶段2: /api/v1/generate 返回 2 张图 URL (效果图+平面图) (2026-08-04)" >> docs/gallery/smoke-test.md
echo "- 阶段2: /images/{scheme_id}/facade.png 可访问 (200)" >> docs/gallery/smoke-test.md
echo "- 阶段2: 前端表单下方展示效果图与平面图" >> docs/gallery/smoke-test.md
```

- [ ] **Step 5: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 记录阶段 2 冒烟验证结果"
```

---

## Self-Review

**Spec coverage(对照阶段 2 设计规格):**
- ✅ 生成器抽象 `Generator` 协议 + `GenerationArtifact` → Task 1
- ✅ 护城河立面文法(参数→线框)→ Task 2
- ✅ 3/4 等轴透视(带体量感)→ Task 3
- ✅ 简单平面示意(外墙+内墙+双语标签)→ Task 4
- ✅ 渲染编排 + Pillow PNG 落盘 → Task 5
- ✅ `SimulatorGenerator` 实现协议 → Task 6
- ✅ API 注入生成器 + StaticFiles 静态交付 → Task 7
- ✅ 前端表单下方展示双图 → Task 8
- ✅ 端到端冒烟 → Task 9

**Placeholder scan:** 无 TBD/TODO。所有代码块含完整实现。Task 7 的 `test_generate_skeleton` 使用 `tmp_path` 显式传入 `cache_dir`,保证测试不污染真实目录。

**Type consistency:**
- `Generator.generate` 签名(Task 1)与 `SimulatorGenerator.generate`(Task 6)、`render_scheme`(Task 5)一致:`(params, scheme_id, out_dir, lang="zh") -> GenerationArtifact`
- `ImageRef.kind` 用 `Literal["facade", "floorplan"]`,renderer 落盘文件名 `facade.png`/`floorplan.png` 与 URL `/images/{scheme_id}/...` 一一对应
- `GenerationResponse.images` 为 `list[str]`,API 从 artifact 的 `img.url` 提取——契约一致
- 前端 `ResultImages` 通过 `url.includes("facade")` 分类,与后端文件名约定一致

**确定性说明:** 所有绘图由 `BuildingParams` 唯一决定(无随机),测试可复现。透视深度固定 50px、画布固定 640×480/480×360,输出确定。
