# 前端 roof 控件 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端 `ParamForm` 新增 roof 下拉控件(平顶/坡顶/四坡顶),替换当前硬编码 `roof: "flat"`,让用户能选择屋顶类型。

**Architecture:** 纯前端改动。`ParamForm.tsx` 加 `roof` state + 下拉(显示 i18n 本地化标签,提交原始枚举值 flat/pitched/hipped),i18n 加 4 个 key。后端零改动(roof 已支持,模拟器有几何差异 + SDXL prompt 有标签)。

**Tech Stack:** React 18 + TypeScript + Vite;i18n 为 JSON key→value;验证 = `tsc && vite build` + 浏览器手动确认。

## Global Constraints

- 后端零改动:`BuildingParams.roof` 已支持 `Literal["flat","pitched","hipped"]`
- roof 选项显示本地化标签,提交值用原始枚举值(flat/pitched/hipped)
- 默认值 `"flat"` 保持现状,无行为变化
- 前端无测试设施,验证 = `tsc && vite build` 通过 + 浏览器手动确认
- 不做:environment 控件(暂缓 follow-up)、api/client.ts 改动(`BuildingParams` 已含 `roof` 字段)
- commit 前缀:`feat:`;消息用中文
- 不改:后端、生成链路、现有控件行为

---

### Task 1: ParamForm 加 roof 下拉 + i18n

**Files:**
- Modify: `frontend/src/components/ParamForm/ParamForm.tsx:19`(state)+ `:35-38`(onSubmit)+ `:68-72`(表单,material 之后加 roof 下拉)
- Modify: `frontend/src/i18n/zh.json`
- Modify: `frontend/src/i18n/en.json`

**Interfaces:**
- Consumes: 无(独立前端改动)
- Produces: `ParamForm` 提交的请求 body 含 `roof`(原始枚举值),可选 `roof_flat`/`roof_pitched`/`roof_hipped` i18n key

- [ ] **Step 1: i18n 加 roof 翻译**

修改 `frontend/src/i18n/zh.json`,在 `"material"` 与 `"generate"` 之间插入:

```json
  "material": "材质", "roof": "屋顶", "roof_flat": "平顶", "roof_pitched": "坡顶", "roof_hipped": "四坡顶", "generate": "生成方案",
```

修改 `frontend/src/i18n/en.json`,同样位置插入:

```json
  "material": "Material", "roof": "Roof", "roof_flat": "Flat", "roof_pitched": "Pitched", "roof_hipped": "Hipped", "generate": "Generate",
```

- [ ] **Step 2: ParamForm 加 roof state**

在 `frontend/src/components/ParamForm/ParamForm.tsx:19`(`material` state 之后)加:

```tsx
  const [roof, setRoof] = useState("flat");
```

- [ ] **Step 3: onSubmit 用 roof state**

修改 `frontend/src/components/ParamForm/ParamForm.tsx` onSubmit 里(当前 `:36` 的 `roof: "flat",`):

把:
```tsx
          roof: "flat",
```
替换为:
```tsx
          roof,
```

- [ ] **Step 4: 表单加 roof 下拉**

在 `frontend/src/components/ParamForm/ParamForm.tsx` 的 material `<label>`(当前 `:68-72`)之后、提交按钮之前,加:

```tsx
        <label>{messages.roof}
          <select value={roof} onChange={(e) => setRoof(e.target.value)}>
            <option value="flat">{messages.roof_flat}</option>
            <option value="pitched">{messages.roof_pitched}</option>
            <option value="hipped">{messages.roof_hipped}</option>
          </select>
        </label>
```

- [ ] **Step 5: 前端 build 验证**

Run: `cd frontend && npm run build`
Expected: `tsc && vite build` 通过,无 TS 类型错误

- [ ] **Step 6: 后端全量回归(确认零回归)**

Run: `cd .. && uv run pytest -q`
Expected: 95 passed + 1 skipped(roof 后端测试已覆盖,无新增失败)

- [ ] **Step 7: ruff + 提交**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 双绿

```bash
git add frontend/src/components/ParamForm/ParamForm.tsx frontend/src/i18n/zh.json frontend/src/i18n/en.json
git commit -m "feat: 前端 ParamForm 新增 roof 下拉控件(平顶/坡顶/四坡顶)"
```

---

### Task 2: 浏览器验证 + smoke-test 记录

**Files:**
- Modify: `docs/gallery/smoke-test.md`
- Modify: `.claude/settings.json`(若需加 dev server 配置)

**Interfaces:**
- Consumes: Task 1 全部改动
- Produces: 冒烟验证记录(roof 控件生效证据)

- [ ] **Step 1: 启动后端**

Run(主工作区根目录): `uv run archgen-api`
Expected: FastAPI 启动,`/api/v1/generate` 可调

- [ ] **Step 2: 启动前端 dev server**

Run: `cd frontend && npm run dev`
Expected: Vite dev server 启动(默认 http://localhost:5173)

- [ ] **Step 3: 浏览器验证 roof 生效**

在浏览器操作:
1. 打开 http://localhost:5173 → 表单出现「屋顶」下拉(默认「平顶」)
2. 选「坡顶」→ 生成 → 结果效果图屋顶为坡面(与平顶出图对比不同)
3. 选「四坡顶」→ 生成 → 结果效果图屋顶为四坡
4. 切换 EN → 下拉显示 Roof/Flat/Pitched/Hipped
5. 提交时 Network 面板确认请求 body 含 `"roof":"pitched"`(原始枚举值)

- [ ] **Step 4: 追加 smoke-test 记录**

在 `docs/gallery/smoke-test.md` 末尾追加:

```markdown
# 前端 roof 控件验证记录 (2026-08-12)

- ParamForm 新增「屋顶」下拉(平顶/坡顶/四坡顶),默认「平顶」,替换硬编码 roof: "flat"
- 提交值用原始枚举值(flat/pitched/hipped);下拉显示 i18n 本地化标签(中文/英文)
- 浏览器验证:选「坡顶」「四坡顶」生成 → 效果图屋顶随选择变化;EN 切换显示 Flat/Pitched/Hipped
- 后端零改动(roof 已有模拟器几何 + SDXL prompt 支持);全量回归 95 passed + 1 skipped
- 遗留:environment 控件暂缓(模拟器模式无视觉差异,留待真调验证阶段)
```

- [ ] **Step 5: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 前端 roof 控件验证记录(浏览器确认生效 + 全量回归)"
```

---

## 验收标准(对照设计文档)

| 设计要求 | 对应任务 | 验证 |
|---|---|---|
| ParamForm 新增 roof 下拉(平顶/坡顶/四坡顶) | Task 1 Step 4 | 表单显示「屋顶」下拉,3 选项 |
| 提交值用原始枚举值(flat/pitched/hipped) | Task 1 Step 3 | Network 请求 body `"roof":"pitched"` |
| 下拉显示 i18n 本地化标签(中/英) | Task 1 Step 1 | 浏览器中英切换正确显示 |
| 默认 flat 保持现状 | Task 1 Step 2 | 默认下拉为「平顶」 |
| 后端零改动 | 全计划 | diff 检查,roof 后端测试已覆盖 |
| environment 暂缓(follow-up) | 全计划 | smoke-test 记录遗留项 |
