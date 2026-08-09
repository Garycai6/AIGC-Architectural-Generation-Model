# 阶段 4:前端语言切换 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 激活中英双语——标题旁顶部加切换按钮,`messages` 随语言切换,`lang` 同步传 `/generate`。

**Architecture:** 新增 `LangContext`(React Context,localStorage 持久化),`LangProvider` 提供 `{ lang, setLang, messages }`。`App.tsx` 包裹 Provider + 顶部切换按钮;`ParamForm` 从 `useLang()` 取 `lang`/`messages`,替代写死的 `"zh"`。

**Tech Stack:** React 18、Vite、TypeScript(无新依赖)。

## Global Constraints

- 前端 React + Vite + TypeScript(strict mode)
- 双语文案统一放 `frontend/src/i18n/{en,zh}.json`,硬编码散落中文字符串视为缺陷
- `npm run build`(tsc + vite build)必须通过,零类型错误
- 提交信息用 `feat:` / `fix:` / `docs:` 前缀
- 不改后端契约(`GenerateRequest.lang` 已存在)
- localStorage key 固定为 `archgen_lang`,值 `"zh" | "en"`
- `LangContext` 放 `src/contexts/`(语言资源 i18n/ 与状态 contexts/ 分离)

---

### Task 1: LangContext(LangProvider + useLang)

**Files:**
- Create: `frontend/src/contexts/LangContext.tsx`
- Create: `frontend/src/contexts/index.ts`(可选,聚合导出)

**Interfaces:**
- Consumes: `zh.json` / `en.json`(已有)
- Produces:
  - `type Lang = "zh" | "en"`
  - `type LangMessages = typeof zh`(语言 json 的类型)
  - `LangProvider({ children }: { children: React.ReactNode })` — Context Provider,state `lang` 初始从 `localStorage["archgen_lang"]` 读(无则 `"zh"`),`setLang` 写 localStorage
  - `useLang(): { lang: Lang, setLang: (l: Lang) => void, messages: LangMessages }` — 在 Provider 外抛错

- [ ] **Step 1: 创建 LangContext.tsx**

```tsx
// frontend/src/contexts/LangContext.tsx
import { createContext, useContext, useState, type ReactNode } from "react";
import en from "../i18n/en.json";
import zh from "../i18n/zh.json";

export type Lang = "zh" | "en";
export type LangMessages = typeof zh;

const STORAGE_KEY = "archgen_lang";

interface LangContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  messages: LangMessages;
}

const LangContext = createContext<LangContextValue | null>(null);

function initialLang(): Lang {
  const stored = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
  return stored === "en" ? "en" : "zh";
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = (l: Lang) => {
    setLangState(l);
    localStorage.setItem(STORAGE_KEY, l);
  };

  return (
    <LangContext.Provider value={{ lang, setLang, messages: lang === "zh" ? zh : en }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used within LangProvider");
  return ctx;
}
```

- [ ] **Step 2: 创建 contexts 聚合导出**

```ts
// frontend/src/contexts/index.ts
export { LangProvider, useLang } from "./LangContext";
export type { Lang, LangMessages } from "./LangContext";
```

- [ ] **Step 3: 运行 TypeScript 编译验证**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/contexts/
git commit -m "feat: 添加 LangContext(LangProvider + useLang, localStorage 持久化)"
```

---

### Task 2: App.tsx 包裹 Provider + 顶部切换按钮

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `LangProvider`/`useLang`(Task 1)
- Produces: 标题旁切换按钮,点击切换语言

- [ ] **Step 1: 修改 App.tsx**

```tsx
// frontend/src/App.tsx
import ParamForm from "./components/ParamForm/ParamForm";
import { LangProvider, useLang } from "./contexts";

function ToggleLang() {
  const { lang, setLang } = useLang();
  return (
    <button
      onClick={() => setLang(lang === "zh" ? "en" : "zh")}
      style={{ marginLeft: "auto", cursor: "pointer" }}
    >
      {lang === "zh" ? "EN" : "中文"}
    </button>
  );
}

function AppInner() {
  const { messages } = useLang();
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <h1>{messages.app_title}</h1>
        <ToggleLang />
      </div>
      <ParamForm />
    </div>
  );
}

export default function App() {
  return (
    <LangProvider>
      <AppInner />
    </LangProvider>
  );
}
```

- [ ] **Step 2: 运行 build 验证**

Run: `cd frontend && npm run build`
Expected: TypeScript 编译 + Vite build 通过。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.tsx
git commit -m "feat: 标题旁顶部语言切换按钮(EN/中文)"
```

---

### Task 3: ParamForm 使用 useLang(替代写死 zh)

**Files:**
- Modify: `frontend/src/components/ParamForm/ParamForm.tsx`

**Interfaces:**
- Consumes: `useLang`(Task 1)
- Produces: `messages`/`lang` 来自 `useLang`,`generateScheme` 传 `lang`

- [ ] **Step 1: 修改 ParamForm.tsx**

关键改动(保留现有表单字段与结果展示逻辑,只改两处):
1. import 处:`import { messages } from "../../i18n"` → `import { useLang } from "../../contexts"`
2. 组件内:顶部加 `const { lang, messages } = useLang();`(现有各 `useState` 之后)
3. `generateScheme({...}, "zh")` → `generateScheme({...}, lang)`

```tsx
// frontend/src/components/ParamForm/ParamForm.tsx
import { useState } from "react";
import { generateScheme } from "../../api/client";
import { useLang } from "../../contexts";

const STYLES = ["modern", "neoclassic", "european", "nordic"];
const MATERIALS = ["glass", "stone", "brick", "wood"];

interface ResultImages {
  facade?: string;
  floorplan?: string;
}

export default function ParamForm() {
  const { lang, messages } = useLang();
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
        lang  // 替代写死的 "zh"
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

  // ... 以下 form/结果展示 JSX 保持不变(已用 messages.*)
}
```

> **注意:** `i18n/index.ts` 的旧 `messages` 导出不再被 App/ParamForm 使用。保留它(不删)——它是纯 json 加载,无副作用,且可能是其他代码的入口。若实施时发现无任何引用,可删,但保守起见先保留。

- [ ] **Step 2: 运行 build 验证**

Run: `cd frontend && npm run build`
Expected: TypeScript 编译 + Vite build 通过。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ParamForm/ParamForm.tsx
git commit -m "feat: ParamForm 用 useLang 切换语言并同步 lang 传后端"
```

---

### Task 4: 端到端验证(阶段 4 完成标准)

**Files:**
- Modify: `docs/gallery/smoke-test.md`(追加阶段 4 记录)

**Interfaces:**
- Consumes: Task 1-3 全部产物

- [ ] **Step 1: 运行 build 与后端测试**

Run:
```bash
cd frontend && npm run build
cd .. && uv run pytest -q
```
Expected: build 通过,后端 56 测试全绿。

- [ ] **Step 2: 启动前后端,浏览器验证语言切换**

Run(终端 A): `uv run archgen-api`
Run(终端 B): `cd frontend && npm run dev`
Expected: Vite 5173 启动。

浏览器访问 `http://localhost:5173`:
1. 默认中文界面,标题「ArchGen 建筑方案生成」,表单「风格/层数/面宽/进深/材质/生成方案」
2. 点顶部「EN」按钮 → 全部文案变英文(Style/Floors/Width/Depth/Material/Generate)
3. 切回「中文」→ 恢复中文
4. 刷新页面 → 语言保持上次选择(localStorage 持久化)
5. 英文状态下生成 → 平面图房间标签为英文;中文状态 → 中文

- [ ] **Step 3: 记录冒烟结果**

```bash
echo "- 阶段4: 语言切换按钮(标题旁顶部),localStorage 持久化" >> docs/gallery/smoke-test.md
echo "- 阶段4: messages 随语言切换,generateScheme 同步传 lang" >> docs/gallery/smoke-test.md
echo "- 阶段4: 刷新保持语言,平面图标签/描述随 lang 变" >> docs/gallery/smoke-test.md
```

- [ ] **Step 4: 提交**

```bash
git add docs/gallery/smoke-test.md
git commit -m "docs: 记录阶段 4 前端语言切换验证结果"
```

---

## Self-Review

**Spec coverage(对照阶段 4 设计规格):**
- ✅ LangContext(LangProvider + useLang,localStorage 持久化)→ Task 1
- ✅ 标题旁顶部切换按钮 → Task 2
- ✅ ParamForm 用 useLang,lang 同步传后端 → Task 3
- ✅ 端到端验证 → Task 4

**Placeholder scan:** 无 TBD/TODO。所有代码块含完整实现。Task 3 的 `i18n/index.ts` 旧导出保留策略已注明。

**Type consistency:**
- `useLang()` 返回 `{ lang, setLang, messages }` 在 Task 1 定义、Task 2/3 消费,签名一致
- `Lang = "zh" | "en"` 贯穿;`generateScheme(params, lang)` 已支持 `lang`
- `LangMessages = typeof zh` 保证 json 键的类型安全

**兼容性:** 后端 `GenerateRequest.lang` 已支持 "en"/"zh",前端传 `lang` 无契约变化。现有 56 测试不受前端改动影响。
