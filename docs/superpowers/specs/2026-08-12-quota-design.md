# 免费额度限制(Quota)设计规格

> 日期:2026-08-12
> 状态:已批准
> 目标:为 ArchGen 网页产品打通「免费→限时」闭环——每个匿名访客每天可免费生成 N 次,超限返回 429。付费解锁留待后续独立子项目。

## 背景与动机

Freemium 商业模式的核心是「免费低分辨率、付费解锁高清/多角度/批量」。`Settings.max_free_quota` 已预留但从未实现额度逻辑。本期落地免费额度限制:匿名访客每天免费生成 N 次,超限拒绝,前端展示剩余次数。付费解锁是独立子系统(需用户账号/支付),不在本期范围。

## 需求(已与用户确认)

| 决策点 | 结论 |
|---|---|
| 范围 | 免费额度限制(计数 + 超额拒绝 + 前端剩余额度展示) |
| 计数维度 | 匿名访客 ID(前端 localStorage 生成,请求头传递) |
| 超限行为 | 每日重置(按日期自然过期,无定时器) |
| 计数范围 | 所有生成路径(simulator 与 replicate)都计入同一免费额度 |
| 持久化 | 内存存储(重启清零;付费那期再引入持久化) |

## 架构

```
frontend                         backend
┌──────────────┐                 ┌──────────────────────────────┐
│ localStorage │  X-Visitor-Id   │ create_app()                 │
│  visitor_id  │ ──────────────> │  app.state.quota_service     │
│  (首次生成   │                 │  └─ QuotaService(max=5)     │
│   UUID)      │                 │      内存 dict:              │
│              │  POST /generate │      {visitor: {date: count}}│
│  client.ts 头│ ──────────────> │  generate 路由:              │
│              │                 │  读头→consume→超限 429       │
└──────────────┘                 └──────────────────────────────┘
```

### 组件

1. **`QuotaService`**(新增 `backend/app/core/quota.py`)
   - 纯逻辑类,零 FastAPI 依赖,单测直白
   - `__init__(self, max_free_quota: int)`
   - `consume(visitor_id: str, date_str: str) -> int` — 消费一次,返回**本次消费后的剩余次数**(≥0)。超限返回 0 且不累加。
   - `remaining(visitor_id: str, date_str: str) -> int` — 查询剩余次数(只读)
   - 内部:`dict[str, dict[str, int]]`,外键 `visitor_id`,内键 `date_str`(`YYYY-MM-DD`);新的一天自然出现新 key,无需定时器
   - 线程安全:`threading.Lock` 保护计数操作(uvicorn 默认单 worker,但加锁成本极低、语义正确)

2. **`create_app`**(修改 `backend/app/main.py`)
   - 构造 `QuotaService(settings.max_free_quota)` 挂到 `app.state.quota_service`(与现有 `app.state.settings` 同模式,测试可注入)

3. **`generate` 路由**(修改 `backend/app/api/generate.py`)
   - 开头读请求头 `X-Visitor-Id`
   - 无该头 → 放行(向后兼容,老前端/curl 不受影响)
   - 有该头 → `quota_service.consume(visitor_id, today)` → 返回 0 → 抛 `HTTPException(429, detail="今日免费额度已用完")`
   - `today` 用服务器本地日期 `YYYY-MM-DD`
   - 超限时抛 `HTTPException(429, "今日免费额度已用完")`,响应体为 FastAPI 标准错误体 `{"detail": "今日免费额度已用完"}`(不含 `remaining_quota`;前端对 429 直接读 `detail` 展示文案)

4. **响应体**(修改 `backend/app/schemas/generate.py`)
   - `GenerationResponse` 增加 `remaining_quota: int` 字段(本次消费后的剩余次数);200 响应带此字段供前端展示
   - 注意:429 由 `HTTPException` 抛出,响应体是 FastAPI 标准 `{"detail": "..."}`,**不含** `remaining_quota`;前端对 200 读 `remaining_quota`,对 429 读 `detail` 展示文案

5. **前端**
   - `client.ts`:`getVisitorId()` 读 `localStorage.getItem("archgen_visitor_id")`,无则 `crypto.randomUUID()` 生成并持久化;`generateScheme` 的 fetch 头加 `X-Visitor-Id`
   - `ParamForm.tsx`:解析 `remaining_quota`,结果区显示「今日剩余生成次数:N」;429 时显示「今日免费额度已用完」(i18n)
   - `i18n`:`zh.json`/`en.json` 各加 `quota_remaining`、`quota_exhausted` 两个 key

## 数据流(一次免费生成)

1. 前端加载 → 无 `visitor_id` → `crypto.randomUUID()` 生成并存 localStorage
2. 用户点生成 → `POST /api/v1/generate` 带 `X-Visitor-Id: <uuid>`
3. 后端读头 → `quota_service.consume(id, today)` → 未超限 → 生成并返回 200,`remaining_quota` = 剩余次数
4. 第 6 次 → `consume` 返回 0 → 抛 429 → 前端显示「今日免费额度已用完」

## 错误处理

| 场景 | 行为 |
|---|---|
| 超限(第 6 次) | `HTTPException(429, "今日免费额度已用完")`,响应体为 FastAPI 标准 `{"detail": "今日免费额度已用完"}`;前端对 429 直接读 `detail` 展示文案 |
| 额度内 | 200 正常出图,`remaining_quota` 为剩余次数 |
| 无 `X-Visitor-Id` 头 | 放行(向后兼容) |
| 非法 visitor_id | 按普通 id 处理,不特判 |

## 测试策略

对照现有 `tests/test_api.py` 模式,`_make_app` 已显式传 `max_free_quota=5`,无需改动:

| 层级 | 用例 |
|---|---|
| 单元(`tests/test_quota.py`) | `consume` 限额内返回剩余>0、超限返回 0、不同日期重置、不同访客隔离、`remaining` 只读计数正确 |
| 路由(`tests/test_api.py`) | 无头请求放行(现有测试已覆盖);同一访客第 6 次 → 429;`remaining_quota` 在 200 响应正确递减,429 响应为标准错误体 |
| 回归 | 现有 95 passed + 1 skipped 全绿 |

## 明确不做(本期)

- 付费解锁、支付、用户账号(付费那期再引入持久化)
- 额度状态持久化到文件/数据库(重启清零)
- 登录用户维度计数、多设备同步
- replicate 单独配额(所有路径计入同一免费额度)
- 降低分辨率/加水印的降级出图(未来付费解锁的激励,不在本期)
