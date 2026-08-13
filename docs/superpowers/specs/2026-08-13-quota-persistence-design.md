# Quota 持久化设计规格

> 日期:2026-08-13
> 状态:已批准
> 目标:消除 quota 免费额度「内存存储重启清零」的生产缺陷——额度状态持久化到 JSON 文件,重启不丢。

## 背景与动机

Quota 免费额度限制(2026-08-12)已落地:匿名访客每天 N 次免费生成,`QuotaService` 用内存 dict 计数。已知缺陷:**内存存储重启清零**——线上重启一次用户免费额度全归零,可被反复刷。本期补上 JSON 文件持久化,重启后额度保留。

## 需求(已与用户确认)

| 决策点 | 结论 |
|---|---|
| 持久化选型 | JSON 文件(零依赖,与纯逻辑风格一致) |
| 写入时机 | 每次 consume 后同步写盘 |
| 数据淘汰 | 定期清理旧日期(每 100 次写,清理 >7 天前的访客记录) |
| 加载时机 | QuotaService 构造时同步读文件(若存在) |
| 损坏容错 | 文件损坏/解析失败 → 降级空 dict + warning(服务可用,额度清零可接受) |

## 架构

### 组件

1. **`backend/app/core/quota.py`** — `QuotaService` 扩展
   - `__init__(self, max_free_quota: int, storage_path: Path | None = None)`
     - `storage_path=None`(默认)→ 纯内存模式,现有行为与测试完全不变
     - 非 None → 构造时加载文件(损坏/缺失 → 空 dict + `logging.warning`)
   - `consume(visitor_id, date_str) -> int` — 内存更新后同步写盘(原子写)
   - `remaining(visitor_id, date_str) -> int` — 只读查询,不写盘
   - 私有 `_persist()` — 序列化 `_counts` 为 JSON,原子写
   - 私有 `_maybe_prune()` — 每 100 次写触发,清理 `date < today-7天` 的记录

2. **`backend/app/core/config.py`** — `Settings` 加字段
   - `quota_storage_path: str = ""` — 空=不持久化(内存模式,向后兼容);非空=JSON 文件路径

3. **`backend/app/main.py`** — `create_app`
   - `QuotaService(settings.max_free_quota, storage_path=settings.quota_storage_path or None)`

### 持久化格式

JSON 文件,内容为 `_counts` dict 的直接序列化(无额外结构):

```json
{
  "visitor-abc": {"2026-08-13": 3, "2026-08-12": 2},
  "visitor-def": {"2026-08-13": 1}
}
```

### 原子写

写盘用「同目录临时文件 + `os.replace`」,崩溃不产生半截文件:

```python
def _persist(self) -> None:
    tmp = self._storage_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(self._counts), encoding="utf-8")
    os.replace(tmp, self._storage_path)
```

### 清理策略

每 100 次 `consume` 触发一次:删除 `_counts` 中所有日期早于 `today - 7天` 的 key(访客整体清空则删除该访客 key)。防文件无限增长,验证期访客量小,100 次写一清开销可忽略。

## 数据流

1. 构造:`QuotaService(5, storage_path=...)` → 文件存在则加载到 `_counts`
2. `consume(visitor, today)` → 内存更新 → `_persist()` 原子写盘 → 返回剩余次数
3. 每 100 次写:`_maybe_prune()` 清理 7 天前记录 → `_persist()` 落盘
4. `remaining(visitor, today)` → 只读返回剩余,不写盘

## 错误处理

| 场景 | 行为 |
|---|---|
| 文件不存在(首次启动) | 空 dict,正常启动 |
| 文件损坏/JSON 解析失败 | 空 dict + `logging.warning`(服务可用,额度清零可接受) |
| 写盘失败(磁盘满/权限) | 记 `logging.error`,内存计数继续(下次 consume 重试写);不抛给请求 |
| `storage_path=None` | 纯内存,跳过一切读写 |

## 测试策略

| 层级 | 用例 |
|---|---|
| 单元(`tests/test_quota.py`) | 消费后文件存在且内容正确;重新构造 → 计数保留;损坏文件 → 降级空 dict;清理逻辑剔除 >7 天记录且保留近记录 |
| 路由(`tests/test_api.py`) | 带 `quota_storage_path` 的 Settings → 端到端持久化;默认空 → 内存模式现有测试不变 |
| 回归 | 现有 102 passed + 1 skipped + 新增,全绿;ruff check + format 双绿 |

## 明确不做(本期)

- 多 worker 跨进程同步(当前单 worker 部署,`threading.Lock` 已够;多 worker 需文件锁/换存储)
- SQLite / 数据库持久化
- 登录用户维度持久化(仍是匿名访客 ID)
- 清理策略可配置化(固定 7 天、100 次写,验证期足够)

## 配置示例

生产启用持久化(.env):

```
QUOTA_STORAGE_PATH=.cache/archgen/quota.json
```

留空则保持内存模式(默认,向后兼容)。
