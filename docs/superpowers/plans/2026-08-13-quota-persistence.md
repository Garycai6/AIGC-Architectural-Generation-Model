# Quota 持久化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 quota 免费额度「内存存储重启清零」缺陷——额度状态持久化到 JSON 文件,重启后计数保留。

**Architecture:** `QuotaService` 加可选 `storage_path` 参数(None=纯内存模式,向后兼容);构造时加载文件,每次 `consume` 后原子写盘(`.tmp` + `os.replace`);每 100 次写清理 >7 天前的访客记录。`Settings` 加 `quota_storage_path`(空=内存模式),`create_app` 传给它。

**Tech Stack:** Python 3.11 / FastAPI / pydantic-settings / pytest + ruff(E/F/I/UP/B, line-length=100)。

## Global Constraints

- ruff:`line-length = 100`,`select = ["E", "F", "I", "UP", "B"]`,check + format 双绿
- commit 前缀:`feat:` / `fix:` / `docs:`;消息用中文
- `storage_path=None`(默认)→ 纯内存模式,现有行为与测试**完全不变**(现有 `tests/test_quota.py` 全部不传 storage_path)
- 原子写:同目录 `.tmp` 临时文件 + `os.replace`,崩溃不产生半截文件
- 损坏容错:文件损坏/JSON 解析失败 → 空 dict + `logging.warning`(服务可用,额度清零可接受)
- 写盘失败 → `logging.error`,内存计数继续(下次 consume 重试写);不抛给请求
- 淘汰:每 100 次 consume 触发,清理 `date < today-7天` 的 key(访客整体清空则删该访客 key),清完再写盘一次
- 不改:前端、`generate.py` 路由逻辑、`QuotaService.consume/remaining` 现有行为与返回语义
- 设计文档 `docs/superpowers/specs/2026-08-13-quota-persistence-design.md` 为唯一需求来源,若实现需偏离须先经用户批准

---

### Task 1: QuotaService 持久化(加载 + 写盘 + 清理)

**Files:**
- Modify: `backend/app/core/quota.py`
- Test: `tests/test_quota.py`(末尾追加持久化测试)

**Interfaces:**
- Consumes: 现有 `QuotaService(max_free_quota: int)`(不传 storage_path 时行为不变)
- Produces:
  - `QuotaService.__init__(self, max_free_quota: int, storage_path: Path | None = None)`
  - 非 None 时构造加载(storage_path 文件存在 → 载入 `_counts`;损坏/缺失 → 空 dict + warning)
  - `consume(visitor_id, date_str)` — 内存更新后 `_persist()`(storage_path 非 None 时)
  - `_persist()` — 原子写盘;写失败 `logging.error` 不抛
  - `_maybe_prune(today_str: str)` — 每 100 次写触发,清理 `date < today-7天` 记录

- [ ] **Step 1: 写失败测试(追加到 tests/test_quota.py 末尾)**

```python
import json
from pathlib import Path

from backend.app.core.quota import QuotaService


def test_persist_writes_file_after_consume(tmp_path: Path):
    storage = tmp_path / "quota.json"
    q = QuotaService(max_free_quota=3, storage_path=storage)
    q.consume("v1", "2026-08-13")
    assert storage.exists()
    data = json.loads(storage.read_text(encoding="utf-8"))
    assert data == {"v1": {"2026-08-13": 1}}


def test_persist_restores_counts_on_reconstruct(tmp_path: Path):
    storage = tmp_path / "quota.json"
    q1 = QuotaService(max_free_quota=3, storage_path=storage)
    q1.consume("v1", "2026-08-13")
    q1.consume("v1", "2026-08-13")
    # 模拟重启:重新构造 → 计数保留
    q2 = QuotaService(max_free_quota=3, storage_path=storage)
    assert q2.remaining("v1", "2026-08-13") == 1
    assert q2.consume("v1", "2026-08-13") == 0  # 继续累减,不重置


def test_persist_corrupt_file_falls_back_to_empty(tmp_path: Path):
    storage = tmp_path / "quota.json"
    storage.write_text("{not-valid-json", encoding="utf-8")
    q = QuotaService(max_free_quota=3, storage_path=storage)
    assert q.remaining("v1", "2026-08-13") == 3  # 降级空 dict,额度满额


def test_persist_memory_mode_when_storage_none(tmp_path: Path):
    q = QuotaService(max_free_quota=3)
    q.consume("v1", "2026-08-13")
    assert not list(tmp_path.glob("*.json"))  # 无 storage_path 不写盘


def test_persist_prunes_old_dates(tmp_path: Path):
    storage = tmp_path / "quota.json"
    q = QuotaService(max_free_quota=3, storage_path=storage)
    q.consume("v1", "2026-08-01")  # 旧日期(>7 天前)
    q.consume("v1", "2026-08-13")  # 今天
    # 触发清理(每 100 次写)并验证
    for _ in range(100):
        q.consume("v2", "2026-08-13")
    data = json.loads(storage.read_text(encoding="utf-8"))
    assert "2026-08-01" not in data["v1"]  # 旧日期被清掉
    assert "2026-08-13" in data["v1"]  # 近记录保留
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_quota.py -v`
Expected: 新增 5 个 FAIL(当前 `QuotaService.__init__` 不接受 `storage_path`,TypeError)

- [ ] **Step 3: 实现**

重写 `backend/app/core/quota.py`:

```python
import json
import logging
import os
import threading
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PRUNE_INTERVAL = 100
PRUNE_DAYS = 7


class QuotaService:
    """匿名访客每日免费额度计数(JSON 文件持久化,重启保留)。

    结构:`{visitor_id: {date_str: used_count}}`。新的一天出现新 date_str
    即自然重置,无需定时器。storage_path=None 时纯内存(不读写文件)。
    """

    def __init__(self, max_free_quota: int, storage_path: Path | None = None):
        self._max = max_free_quota
        self._storage_path = storage_path
        self._write_count = 0
        self._lock = threading.Lock()
        self._counts: dict[str, dict[str, int]] = {}
        if storage_path is not None:
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._counts = {
                str(k): {str(d): int(v) for d, v in day.items()}
                for k, day in data.items()
            }
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("quota 持久化文件加载失败,降级为空计数: %s", exc)
            self._counts = {}

    def _persist(self) -> None:
        try:
            tmp = self._storage_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._counts), encoding="utf-8")
            os.replace(tmp, self._storage_path)
        except OSError as exc:
            logger.error("quota 持久化写盘失败: %s", exc)

    def _maybe_prune(self) -> None:
        """每 PRUNE_INTERVAL 次写触发,清理 PRUNE_DAYS 天前的记录。"""
        if self._write_count % PRUNE_INTERVAL != 0:
            return
        cutoff = (date.today() - timedelta(days=PRUNE_DAYS)).isoformat()
        self._counts = {
            vid: {d: n for d, n in day.items() if d >= cutoff}
            for vid, day in self._counts.items()
            if any(d >= cutoff for d in day)
        }

    def consume(self, visitor_id: str, date_str: str) -> int:
        """消费一次,返回本次消费后的剩余次数(≥0)。已达上限返回 0 且不累加。"""
        with self._lock:
            per_day = self._counts.setdefault(visitor_id, {})
            used = per_day.get(date_str, 0)
            if used >= self._max:
                return 0
            per_day[date_str] = used + 1
            if self._storage_path is not None:
                self._write_count += 1
                self._maybe_prune()
                self._persist()
            return self._max - (used + 1)

    def remaining(self, visitor_id: str, date_str: str) -> int:
        with self._lock:
            used = self._counts.get(visitor_id, {}).get(date_str, 0)
            return max(self._max - used, 0)
```

注意:`_maybe_prune` 在 `_persist` 前调用,清理后 `_persist` 一次落盘(避免两次写)。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_quota.py -v`
Expected: 全部 PASS(5 新增 + 5 原有)

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check backend/app/core/quota.py tests/test_quota.py && uv run ruff format --check backend/app/core/quota.py tests/test_quota.py`
Expected: 无告警

```bash
git add backend/app/core/quota.py tests/test_quota.py
git commit -m "feat: QuotaService 支持 JSON 文件持久化(构造加载+原子写盘+定期清理)"
```

---

### Task 2: Settings + create_app 接线

**Files:**
- Modify: `backend/app/core/config.py:16`(Settings 加字段)
- Modify: `backend/app/main.py:15`(create_app 传 storage_path)
- Test: `tests/test_api.py`(末尾追加持久化路由测试)+ `tests/test_replicate_gen.py`(Settings 字段测试)

**Interfaces:**
- Consumes:
  - `QuotaService(max_free_quota, storage_path)`(Task 1)
  - `Settings.cache_dir`(现有,默认 `.cache/archgen`)
- Produces:
  - `Settings.quota_storage_path: str = ""` — 空=内存模式(默认,向后兼容)
  - `create_app` 构造 `QuotaService(settings.max_free_quota, storage_path=settings.quota_storage_path or None)`

- [ ] **Step 1: 写失败测试(追加到 tests/test_api.py 末尾)**

```python
def test_generate_quota_persists_across_app_restart(tmp_path):
    from backend.app.core.config import Settings

    storage = tmp_path / "quota.json"
    settings1 = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=2,
        cache_dir=str(tmp_path / "cache1"),
        quota_storage_path=str(storage),
    )
    client1 = TestClient(create_app(settings1))
    headers = {"X-Visitor-Id": "visitor-1"}
    resp1 = client1.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["remaining_quota"] == 1

    # 模拟重启:新的 app 实例、同一 storage_path
    settings2 = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=2,
        cache_dir=str(tmp_path / "cache2"),
        quota_storage_path=str(storage),
    )
    client2 = TestClient(create_app(settings2))
    resp2 = client2.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["remaining_quota"] == 0  # 已用 1,剩 1,本次消费后 0
    resp3 = client2.post("/api/v1/generate", json=_quota_payload(), headers=headers)
    assert resp3.status_code == 429  # 跨重启额度保留,继续计数
```

追加到 `tests/test_replicate_gen.py`(Settings 字段测试,与其他 Settings 测试同文件):

```python
def test_settings_quota_storage_path_default_empty():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=".tmp-test",
    )
    assert settings.quota_storage_path == ""


def test_settings_quota_storage_path_can_be_set():
    from backend.app.core.config import Settings

    settings = Settings(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        image_provider="simulator",
        max_free_quota=5,
        cache_dir=".tmp-test",
        quota_storage_path=".cache/archgen/quota.json",
    )
    assert settings.quota_storage_path == ".cache/archgen/quota.json"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_api.py::test_generate_quota_persists_across_app_restart tests/test_replicate_gen.py::test_settings_quota_storage_path_default_empty tests/test_replicate_gen.py::test_settings_quota_storage_path_can_be_set -v`
Expected: 3 个 FAIL(`quota_storage_path` 字段不存在,Settings 无法接收)

- [ ] **Step 3: 实现**

**修改 `backend/app/core/config.py`** — `max_free_quota` 之后加:

```python
    quota_storage_path: str = ""  # quota 持久化 JSON 文件路径,空=内存模式(重启清零)
```

**修改 `backend/app/main.py`** — `create_app` 的 quota_service 构造改为:

```python
    app.state.settings = settings or get_settings()
    if app.state.settings.quota_storage_path:
        # quota 持久化文件父目录必须先于 QuotaService 构造创建(构造时加载文件)
        pathlib.Path(app.state.settings.quota_storage_path).parent.mkdir(
            parents=True, exist_ok=True
        )
    app.state.quota_service = QuotaService(
        app.state.settings.max_free_quota,
        storage_path=(
            pathlib.Path(app.state.settings.quota_storage_path)
            if app.state.settings.quota_storage_path
            else None
        ),
    )
```

顺序说明:quota_service 构造(第 15 行)在 `cache_dir.mkdir`(第 23 行)之前,所以 quota 父目录 mkdir 必须插在 `app.state.settings` 赋值之后、quota_service 构造之前,不能依赖后面的 cache_dir.mkdir。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_api.py tests/test_replicate_gen.py -v`
Expected: 新增测试 PASS,原有测试仍 PASS(现有测试不传 quota_storage_path → 内存模式)

- [ ] **Step 5: ruff + 提交**

Run: `uv run ruff check backend/app/core/config.py backend/app/main.py tests/test_api.py tests/test_replicate_gen.py && uv run ruff format --check backend/app/core/config.py backend/app/main.py tests/test_api.py tests/test_replicate_gen.py`
Expected: 双绿

```bash
git add backend/app/core/config.py backend/app/main.py tests/test_api.py tests/test_replicate_gen.py
git commit -m "feat: Settings 新增 quota_storage_path 并接线 create_app(空=内存模式)"
```

---

### Task 3: 全量回归 + smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`

**Interfaces:**
- Consumes: Task 1-2 全部改动
- Produces: 冒烟验证记录(持久化生效证据)

- [ ] **Step 1: 全量测试 + ruff 双绿**

Run: `uv run pytest -q`
Expected: 102(原有)+ 5(Task1)+ 1(Task2 路由)+ 2(Task2 Settings)= **110 passed + 1 skipped**(`test_training_skip.py` 本机无 torch 跳过)
Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 双绿

- [ ] **Step 2: 端到端验证持久化**

Run: `QUOTA_STORAGE_PATH=.cache/archgen/quota.json uv run archgen-api`(后台启动)
Run: `curl -X POST http://127.0.0.1:8000/api/v1/generate -H "Content-Type: application/json" -H "X-Visitor-Id: persist-test" -d '{"params":{"style":"modern","floors":3,"width_m":10,"depth_m":8,"materials":["glass"],"roof":"flat","environment":"suburb"},"lang":"zh"}'`(首次 → remaining_quota=4)
Run: 重启后端,再次同样 curl → remaining_quota=3(计数保留,非重置为 4)
Run: `cat .cache/archgen/quota.json` → 内容含 `"persist-test": {"<today>": 2}`

- [ ] **Step 3: 追加 smoke-test 记录**

在 `docs/gallery/smoke-test.md` 末尾追加:

```markdown
# Quota 持久化验证记录 (2026-08-13)

- QuotaService 支持 storage_path(JSON 文件):构造加载,consume 后原子写盘(.tmp+os.replace)
- 每 100 次写清理 7 天前记录;损坏文件降级空 dict;写盘失败记 error 不影响服务
- Settings.quota_storage_path 默认空=内存模式(向后兼容);非空启用持久化
- 端到端:QUOTA_STORAGE_PATH 启动 → 消费 → 重启 → 计数保留继续累减;quota.json 内容正确
- 单测:持久化读写/重启恢复/损坏降级/内存模式不写盘/清理逻辑;路由级跨 app 重启保留
- 全量回归:110 passed + 1 skipped;ruff check + format 双绿
- 遗留:多 worker 跨进程同步(单 worker 部署够用);付费解锁仍留待后续
```

- [ ] **Step 4: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: Quota 持久化验证记录(全量回归 + 端到端重启保留)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| `QuotaService.__init__(max_free_quota, storage_path=None)` | Task 1 | `test_persist_memory_mode_when_storage_none` + 原有测试 |
| 构造加载文件(存在→载入,损坏→空+warning) | Task 1 | `test_persist_restores_counts_on_reconstruct` / `test_persist_corrupt_file_falls_back_to_empty` |
| 每次 consume 后原子写盘 | Task 1 | `test_persist_writes_file_after_consume`(验证 `.tmp`+`os.replace` 语义) |
| 每 100 次写清理 >7 天记录 | Task 1 | `test_persist_prunes_old_dates` |
| 写盘失败记 error 不抛 | Task 1 | 实现 `_persist` 的 `except OSError`(代码审查) |
| `Settings.quota_storage_path` 默认空 | Task 2 | `test_settings_quota_storage_path_default_empty` |
| `create_app` 传 storage_path(空→None) | Task 2 | `test_generate_quota_persists_across_app_restart` |
| 全量回归 110 passed + 1 skipped | Task 3 | `uv run pytest -q` |
| 不改前端/路由逻辑/现有返回语义 | 全计划 | diff 检查 |
