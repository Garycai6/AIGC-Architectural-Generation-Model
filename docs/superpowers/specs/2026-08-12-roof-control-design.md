# 建筑 AIGC 生成模型 — 前端 roof 控件设计

日期:2026-08-12
状态:已确认

## 背景与定位

里程碑 1 遗留 TODO(2026-08-04 记录):前端 roof/environment 控件写死(当前 `roof: "flat"`、`environment: "suburb"` 硬编码在 `ParamForm.tsx`),用户无法选择。

本期只做 **roof 控件**。environment 暂缓——它在模拟器模式(默认,效果图+平面图都模拟器)下不被消费、无视觉差异,只有 replicate 真模型模式才影响 SDXL prompt,真正的价值时刻在真调验证打通后。本期记录为 follow-up。

## 关键事实(确认)

- 后端 `BuildingParams.roof` 已是 `Literal["flat", "pitched", "hipped"]`,模拟器对 3 种屋顶有真实几何差异(flat 平顶 / pitched 坡面屋脊 / hipped 四坡),SDXL prompt 有对应标签 → **纯前端改动,后端零改动**
- 现状:`ParamForm.tsx:36` onSubmit 硬编码 `roof: "flat"`,用户无法选
- 前端无测试设施(纯 `tsc && vite build` 验证);roof 后端测试已完整覆盖(模拟器几何差异 + SDXL prompt 标签)
- i18n 为纯 JSON key→value 结构(`LangContext` 按 lang 取 zh/en)

## 架构(组件 + 数据流)

```
select 选 平顶/坡顶/四坡顶
  └── roof state (ParamForm.tsx)
        └── generateScheme({ ..., roof }, lang)   # 提交原始枚举值 flat/pitched/hipped
              └── POST /api/v1/generate → BuildingParams.roof 校验
                    └── 模拟器 roof 几何 / SDXL prompt roof 标签
```

## 组件改动

### 1. `frontend/src/components/ParamForm/ParamForm.tsx`

- 新增 state:`const [roof, setRoof] = useState("flat")`(默认 flat 保持现状,无行为变化)
- 表单新增下拉,置于 material 之后、提交按钮之前:

```tsx
<label>{messages.roof}
  <select value={roof} onChange={(e) => setRoof(e.target.value)}>
    <option value="flat">{messages.roof_flat}</option>
    <option value="pitched">{messages.roof_pitched}</option>
    <option value="hipped">{messages.roof_hipped}</option>
  </select>
</label>
```

- onSubmit 去掉硬编码 `roof: "flat"`,改用 state:`roof,`(替换为 `roof,`)

### 2. i18n — `frontend/src/i18n/zh.json` / `en.json`

新增 4 个 key:

| key | zh | en |
|---|---|---|
| `roof` | 屋顶 | Roof |
| `roof_flat` | 平顶 | Flat |
| `roof_pitched` | 坡顶 | Pitched |
| `roof_hipped` | 四坡顶 | Hipped |

## 测试策略

- **前端**:无测试设施,验证 = `tsc && vite build` 通过 + 浏览器手动确认(选不同 roof 出图屋顶变化)
- **后端**:零改动,roof 已有完整测试;现有 95 tests 不回归
- **关键验收**:选「四坡顶」生成 → 请求 body 里 `roof: "hipped"` → 出图屋顶为四坡

## 交付边界

- 代码:`ParamForm.tsx` + `zh.json` + `en.json`
- 验证:`tsc && vite build` 通过 + 手动浏览器确认 roof 生效
- 不做:environment 控件(暂缓 follow-up)、后端任何改动、roof 视觉本身(模拟器已支持)

## 与现有代码关系

- 不改:后端、生成链路、`api/client.ts`(`BuildingParams` 接口已含 `roof` 字段)
- 复用:i18n 现有 JSON key→value 模式、style/material 下拉模式
- 不引入新依赖、新测试设施
