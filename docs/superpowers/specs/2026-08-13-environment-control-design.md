# 前端 environment 下拉控件 设计规格

> 日期:2026-08-13
> 状态:已批准
> 目标:前端 `ParamForm` 新增「环境」下拉控件(城市/郊区/乡村/海滨),替换当前硬编码 `environment: "suburb"`,让用户能选择场地环境。

## 背景与动机

roof 控件(2026-08-12)已落地,验证记录中遗留「environment 控件暂缓(模拟器模式无视觉差异,留待真调验证阶段)」。现补上姊妹控件:纯前端改动,后端 `BuildingParams.environment` 已支持 `Literal["urban", "suburb", "rural", "seaside"]`,SDXL prompt 已消费(`ENVIRONMENT_LABELS[params.environment]`)。模拟器模式 environment 无视觉差异是已知特性,真调阶段 replicate 模式 prompt 生效。

## 需求(已与用户确认)

| 决策点 | 结论 |
|---|---|
| 显示标签 | i18n 双语标签(与 roof 控件一致),提交值用原始枚举值 |
| 默认值 | `"suburb"`(保持现状,无行为变化) |
| 改动范围 | 纯前端,后端零改动 |

## 架构

### 组件(与 roof 控件完全同构)

1. **`frontend/src/components/ParamForm/ParamForm.tsx`**
   - 常量 `const ENVIRONMENTS = ["urban", "suburb", "rural", "seaside"]`(与现有 `STYLES`/`MATERIALS` 常量同风格)
   - state `const [environment, setEnvironment] = useState("suburb")`
   - onSubmit 把硬编码 `environment: "suburb"` 改为 `environment`
   - roof 下拉 `<label>` 之后、提交按钮之前,加 environment 下拉 `<label>`

2. **`frontend/src/i18n/zh.json`** — 加 5 个 key:`environment`(环境)、`environment_urban`(城市)、`environment_suburb`(郊区)、`environment_rural`(乡村)、`environment_seaside`(海滨)

3. **`frontend/src/i18n/en.json`** — 加 5 个 key:`environment`(Environment)、`environment_urban`(Urban)、`environment_suburb`(Suburb)、`environment_rural`(Rural)、`environment_seaside`(Seaside)

### 下拉结构(与 roof 下拉同构)

```tsx
        <label>{messages.environment}
          <select value={environment} onChange={(e) => setEnvironment(e.target.value)}>
            {ENVIRONMENTS.map((env) => (
              <option key={env} value={env}>{messages[`environment_${env}` as keyof typeof messages]}</option>
            ))}
          </select>
        </label>
```

(实现细节:若 `messages` 类型不支持动态索引,则像 roof 控件那样显式列出 4 个 `<option>` 行。以 roof 下拉的现有写法为准。)

## 数据流

1. 用户选环境 → `environment` state 更新(默认 suburb)
2. 提交 → `generateScheme` 请求体含原始枚举值(如 `"environment": "seaside"`)
3. 后端 `BuildingParams.environment` 校验 4 枚举值
4. 模拟器模式:environment 无视觉差异(渲染器不读);replicate 模式:SDXL prompt `ENVIRONMENT_LABELS[environment]` 生效

## 错误处理

| 场景 | 行为 |
|---|---|
| 非法 environment | 后端 pydantic 422(已有行为,`Literal` 校验) |
| 前端缺 i18n key | 显示 key 名(不会发生,zh/en 同步加) |

## 测试策略

前端无测试设施,验证 = `tsc && vite build` + 浏览器手动确认:

| 层级 | 用例 |
|---|---|
| build | `cd frontend && npm run build` 通过,无 TS 类型错误 |
| 浏览器 | 中文「环境」下拉默认「郊区」4 选项;切 EN → Environment/Urban/Suburb/Rural/Seaside;提交请求 body 含原始枚举值;模拟器模式 4 环境出图 PNG 可能相同(已知特性,不作为 bug) |
| 回归 | 后端零改动,`uv run pytest -q` 全量 111 passed + 1 skipped 不受影响 |

## 明确不做(本期)

- 后端改动(`environment` 已支持,SDXL prompt 已消费)
- 模拟器环境视觉差异化(渲染器不读 environment,真调阶段才有意义)
- `api/client.ts` 改动(`BuildingParams` 已含 `environment` 字段)
- environment 提交值改中文/本地化(提交用原始枚举值,与 roof 一致)
