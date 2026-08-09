# 阶段 4:前端语言切换 — 设计规格

日期：2026-08-05
状态：已确认
前置：阶段 0/2/2.5/3 已合并到 master(前端参数表单 + i18n 双语 json + 后端 lang 支持)

## 背景与定位

阶段 0 建立了 `frontend/src/i18n/{zh,en}.json` 双语文案,但 `i18n/index.ts` 只加载 zh(`messages = zh` 写死),英文文案是死文件。无切换按钮。阶段 2/2.5/3 遗留的 follow-up 包含「前端写死 lang:"zh"」。

本阶段目标:**激活中英双语**——标题旁顶部加切换按钮,`messages` 随语言切换,`lang` 同步传 `/generate`(平面图房间标签、DeepSeek 描述跟着变)。项目定位是中英双语兼顾、面向公众的 Freemium SaaS,语言切换是产品级功能。

## 关键决策(已确认)

| 决策点 | 结论 |
|---|---|
| 偏好持久化 | localStorage 记住语言偏好(key `archgen_lang`) |
| 按钮位置 | 标题旁顶部 |
| lang 联动 | 切语言同步传 `/generate`(替代写死 "zh") |
| 状态方案 | React Context(`LangProvider` + `useLang`) |
| Context 位置 | `src/contexts/LangContext.tsx`(语言资源 i18n/ 与状态 contexts/ 分离) |

## 架构

```
frontend/src/
├── i18n/                  # 已有:纯语言资源(不改结构)
│   ├── zh.json / en.json  # 已有:文案齐全
│   └── index.ts           # 改造:保留 messages 导出(由 useLang 提供,见下)
├── contexts/
│   └── LangContext.tsx    # 新增:React Context(LangProvider + useLang hook)
├── components/
│   ├── App.tsx            # 改:包裹 LangProvider + 顶部切换按钮
│   └── ParamForm/ParamForm.tsx  # 改:lang 从 useLang 取,替代写死 "zh"
```

## 组件职责

### LangContext.tsx(新增)

- `LangProvider`:
  - state `lang`(初始从 `localStorage["archgen_lang"]` 读,无则默认 `"zh"`)
  - `setLang(lang)`(更新 state + 写 `localStorage["archgen_lang"]`)
- `useLang()`:
  - 返回 `{ lang, setLang, messages }`
  - `messages` = `lang === "zh" ? zh : en`(当前语言 json)
  - 在 Provider 外使用抛错(React 标准模式)

### App.tsx(改)

- 用 `<LangProvider>` 包裹内容
- 标题旁放切换按钮:`{lang === "zh" ? "EN" : "中文"}` 点击切换(setLang 到另一语言)

### ParamForm.tsx(改)

- `const { lang, messages } = useLang()` 替代 `import { messages }`
- `generateScheme(params, lang)` 替代写死 `"zh"`

## 数据流

```
localStorage["archgen_lang"] → LangProvider 初始 lang("zh" 默认)
  用户点切换按钮 → setLang(new) → 写 localStorage + 触发重渲染
  ├─ messages → 全部界面文案(标题/表单/结果标签/错误)变语言
  └─ ParamForm 的 generateScheme(..., lang) → 后端平面图标签/描述同步
```

## 测试策略

- 前端无测试框架配置(package.json 仅 build),验证靠:
  - `npm run build` 通过(TypeScript 编译)
  - 浏览器手动验证:点切换 → 全部文案变英文 → 生成结果平面图标签变英文

## 明确排除(本阶段不做)

- ❌ 不加测试框架(前端目前无 Jest/Vitest,是另一件事)
- ❌ 不引 i18next(轻量 Context 足够)
- ❌ 不改后端(prompt 固定英文是模型输入;平面图标签/描述已支持 lang)

## 对既有约束的遵守

- 双语文案统一放 `frontend/src/i18n/{en,zh}.json`,硬编码散落中文字符串视为缺陷
- `npm run build`(tsc + vite build)必须通过
- 不改后端契约(`GenerateRequest.lang` 已存在)
