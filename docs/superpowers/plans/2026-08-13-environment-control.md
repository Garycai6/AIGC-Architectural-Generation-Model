# 前端 environment 下拉控件 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端 `ParamForm` 新增「环境」下拉控件(城市/郊区/乡村/海滨),替换硬编码 `environment: "suburb"`,让用户能选择场地环境。

**Architecture:** 纯前端改动,与已落地的 roof 控件完全同构。`ParamForm.tsx` 加 `environment` state + 下拉(显示 i18n 本地化标签,提交原始枚举值 urban/suburb/rural/seaside),i18n 加 5 个 key。后端零改动(`BuildingParams.environment` 已支持,SDXL prompt 已消费)。

**Tech Stack:** React 18 + TypeScript + Vite;i18n 为 JSON key→value;验证 = `tsc && vite build` + 浏览器手动确认。

## Global Constraints

- 后端零改动:`BuildingParams.environment` 已支持 `Literal["urban","suburb","rural","seaside"]`
- environment 选项显示本地化标签,提交值用原始枚举值(urban/suburb/rural/seaside)
- 默认值 `"suburb"` 保持现状,无行为变化
- 下拉结构与 roof 下拉同构:显式 `<option>` 行(非 map),与现有 roof 下拉写法一致
- 前端无测试设施,验证 = `tsc && vite build` 通过 + 浏览器手动确认
- 模拟器模式 4 环境出图 PNG 可能相同(渲染器不读 environment)——已知特性,不作为 bug
- 不做:后端改动、`api/client.ts` 改动(`BuildingParams` 已含 `environment` 字段)
- commit 前缀:`feat:`;消息用中文
- 设计文档 `docs/superpowers/specs/2026-08-13-environment-control-design.md` 为唯一需求来源,若实现需偏离须先经用户批准

---

### Task 1: ParamForm 加 environment 下拉 + i18n

**Files:**
- Modify: `frontend/src/components/ParamForm/ParamForm.tsx:20`(state)+ `:39`(onSubmit)+ `:82-83`(表单,roof 之后加 environment 下拉)
- Modify: `frontend/src/i18n/zh.json`
- Modify: `frontend/src/i18n/en.json`

**Interfaces:**
- Consumes: 无(独立前端改动)
- Produces: `ParamForm` 提交的请求 body 含 `environment`(原始枚举值);i18n key `environment` / `environment_urban` / `environment_suburb` / `environment_rural` / `environment_seaside`

- [ ] **Step 1: i18n 加 environment 翻译**

修改 `frontend/src/i18n/zh.json`,在 `"quota_exhausted"` 之后插入(该文件第一行现有内容以 `"quota_exhausted": "今日免费额度已用完"` 结尾):

```json
  "environment": "环境", "environment_urban": "城市", "environment_suburb": "郊区", "environment_rural": "乡村", "environment_seaside": "海滨",
```

修改 `frontend/src/i18n/en.json`,同样位置插入:

```json
  "environment": "Environment", "environment_urban": "Urban", "environment_suburb": "Suburb", "environment_rural": "Rural", "environment_seaside": "Seaside",
```

- [ ] **Step 2: ParamForm 加 environment state**

在 `frontend/src/components/ParamForm/ParamForm.tsx:20`(`roof` state 之后)加:

```tsx
  const [environment, setEnvironment] = useState("suburb");
```

- [ ] **Step 3: onSubmit 用 environment state**

修改 `frontend/src/components/ParamForm/ParamForm.tsx:39`(当前 `environment: "suburb",`):

把:
```tsx
          environment: "suburb",
```
替换为:
```tsx
          environment,
```

- [ ] **Step 4: 表单加 environment 下拉**

在 `frontend/src/components/ParamForm/ParamForm.tsx` 的 roof `<label>`(当前 `:76-82`)之后、提交按钮之前,加:

```tsx
        <label>{messages.environment}
          <select value={environment} onChange={(e) => setEnvironment(e.target.value)}>
            <option value="urban">{messages.environment_urban}</option>
            <option value="suburb">{messages.environment_suburb}</option>
            <option value="rural">{messages.environment_rural}</option>
            <option value="seaside">{messages.environment_seaside}</option>
          </select>
        </label>
```

- [ ] **Step 5: 前端 build 验证**

Run: `cd frontend && npm run build`
Expected: `tsc && vite build` 通过,无 TS 类型错误

- [ ] **Step 6: 后端全量回归(确认零回归)**

Run: `cd .. && uv run pytest -q`
Expected: 111 passed + 1 skipped(environment 后端测试已覆盖,无新增失败)

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/ParamForm/ParamForm.tsx frontend/src/i18n/zh.json frontend/src/i18n/en.json
git commit -m "feat: 前端 ParamForm 新增 environment 下拉控件(城市/郊区/乡村/海滨)"
```

---

### Task 2: 浏览器验证 + smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`

**Interfaces:**
- Consumes: Task 1 全部改动
- Produces: 冒烟验证记录(environment 控件生效证据)

- [ ] **Step 1: 启动后端**

Run(主仓库根目录): `uv run archgen-api`
Expected: FastAPI 启动,`/api/v1/generate` 可调

- [ ] **Step 2: 启动前端 dev server**

Run: `cd frontend && npm run dev`
Expected: Vite dev server 启动(默认 http://localhost:5173)

- [ ] **Step 3: 浏览器验证 environment 生效**

在浏览器操作:
1. 打开 http://localhost:5173 → 表单出现「环境」下拉(默认「郊区」)
2. 选「海滨」→ 生成 → 提交时 Network 面板确认请求 body 含 `"environment":"seaside"`(原始枚举值)
3. 切换 EN → 下拉显示 Environment/Urban/Suburb/Rural/Seaside
4. 模拟器模式:不同 environment 出图 PNG 可能字节相同(已知特性,渲染器不读 environment)——不作为 bug

- [ ] **Step 4: 追加 smoke-test 记录**

在 `docs/gallery/smoke-test.md` 末尾追加:

```markdown
# 前端 environment 控件验证记录 (2026-08-13)

- ParamForm 新增「环境」下拉(城市/郊区/乡村/海滨),默认「郊区」,替换硬编码 environment: "suburb"
- 提交值用原始枚举值(urban/suburb/rural/seaside);下拉显示 i18n 本地化标签(中文/英文)
- 浏览器验证:中文「环境」下拉默认「郊区」四选项;切 EN → Environment/Urban/Suburb/Rural/Seaside
- 提交请求 body 含原始枚举值;模拟器模式 environment 无视觉差异(已知特性,渲染器不读,真调阶段 SDXL prompt 生效)
- 后端零改动(environment 已有参数校验 + SDXL prompt 支持);全量回归 111 passed + 1 skipped
```

- [ ] **Step 5: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 前端 environment 控件验证记录(浏览器确认生效 + 全量回归)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| ParamForm 新增 environment 下拉(城市/郊区/乡村/海滨) | Task 1 Step 4 | 表单显示「环境」下拉,4 选项 |
| 提交值用原始枚举值(urban/suburb/rural/seaside) | Task 1 Step 3 | Network 请求 body `"environment":"seaside"` |
| 下拉显示 i18n 本地化标签(中/英) | Task 1 Step 1 | 浏览器中英切换正确显示 |
| 默认 suburb 保持现状 | Task 1 Step 2 | 默认下拉为「郊区」 |
| 后端零改动 | 全计划 | diff 检查,environment 后端测试已覆盖 |
| 模拟器无视觉差异为已知特性 | 全计划 | smoke-test 记录,不作为 bug |
