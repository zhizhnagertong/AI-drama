# Editor.vue 迁移技术评估

评估对象：`frontend/src/views/Editor.vue`（导演工作台），**2,703 行**（含空行）。
用途：判断这部分能否机械化迁移，以及拆分方式与工期。

## 一、结论

**可以迁移，且不需要重写任何底层交互。** 它"大"但不"深"——是状态密集的 CRUD + 实时进度页，不是 canvas / 拖拽类编辑器。

风险评估：**中低**。不是"低"，因为有 19 个状态、12 个 computed、约 50 个函数互相引用，拆分时容易漏依赖。

## 二、结构实测

| 区块 | 行范围 | 行数 |
|---|---|---|
| `<script setup>` | 1–956 | 955 |
| `<template>` | 958–1695 | 737 |
| `<style scoped>` | 1697–2703 | ~1,000 |

内部构成：

| 项 | 数量 | 说明 |
|---|---|---|
| `ref` / `reactive` | 19 | 项目、剧集、分镜、角色、素材、时间线、任务表、6 组弹窗状态 |
| `computed` | 12 | `doneMap` / `stepState` / `ctaLabel` / `pipelineProgress` / `taskList` 等 |
| 函数 | ~50 | 加载、SSE、批量操作、抽卡、版本管理、时间线、合成导出 |
| Tab 分区 | 5 | `script` / `character` / `board` / `voice` / `final` |
| `<el-dialog>` | 6 | 分镜编辑、角色编辑、单张生成、批量出图、批量出视频、版本编辑 |
| `el-*` 组件 | 46 按钮 / 13 表格列 / 11 表单 / 8 输入 / 6 标签 / 5 空态 | 总量约 120 处 |

## 三、关键发现：没有"硬骨头"

逐项排查浏览器 API 与第三方依赖，结果全部为否或极少：

| 检查项 | 结果 |
|---|---|
| `canvas` / `getContext` | **0** |
| `requestAnimationFrame` | **0** |
| HTML5 拖拽（`draggable` / `dragstart` / `drop`） | **0**（顺序调整是 `moveSb(index, ±1)` 按钮式，非拖拽） |
| ResizeObserver / IntersectionObserver | **0** |
| 第三方 UI / 图形库 | **0**，只依赖 element-plus + vue + vue-router |
| `EventSource`（SSE） | 2 处 —— 唯一的"非普通"能力 |
| `Audio()` | 3 处 —— 角色试听播放 |

也就是说：**没有任何一段逻辑依赖 Vue 的渲染机制，全部是数据流 + 表单 + 弹窗。** 这决定了它属于"拆组件"工作，而非"重写"工作。

## 四、React 迁移会咬人的 5 个点

这些是真正需要留神的地方，其余都是机械替换：

### 1. `batchSel` 是 `Set`，就地修改不触发渲染

```js
const batchSel = ref(new Set())          // Vue: 响应式包装，.add() 能触发更新
batchSel.value.add(id)                   // ✅ Vue 有效
```
React 里 `setBatchSel(prev => { prev.add(id); return prev })`（同一引用）**不会重渲染**。必须 `new Set(prev)`。这是批量选择整块功能失效的典型原因。

### 2. `tasks` 是 `reactive({})` 字典，按键增量写入

```js
tasks[tid] = { ...prev, ...data }        // 直接改属性
```
React 必须整体替换引用，且 SSE 回调里要用函数式更新避免闭包陈旧：

```ts
setTasks(prev => ({ ...prev, [tid]: { ...prev[tid], ...data, task_id: tid } }))
```

### 3. SSE 重连 + 令牌临期预刷新（`connectStream`，237–266 行）

原实现有三层保护，移植时不能简化：
- 连接前若 `accessExpiresAt <= now + 60s`，先 `await refreshOnce()`（否则 EventSource 无法带 Header，会 401 重连风暴）；
- `onerror` 关闭后 3s 重连；
- 卸载时必须 `clearTimeout` + `es.close()`，否则 React StrictMode 双挂载会留下两条连接。

### 4. `showErrorOnce` 用跨调用的模块级变量做 2.5s 聚合

```js
let lastErrText = ''; let errCount = 0; let errTimer = null
```
批量任务同时失败时避免刷屏。这类"跨渲染持久"的计数在 React 里要放 `useRef`，不能用 `useState`（否则每次渲染重置）。

### 5. 6 个弹窗的 `v-model` → 受控 `open`

`el-dialog v-model="xVisible"` 在 antd 是 `open={xOpen} onCancel={...}`，且需在关闭时重置表单（原版靠 `openEditSb` 每次写入）。建议统一封装成 `useDialogForm`。

## 五、推荐拆分方案

单文件 2,700 行不适合直接搬，按职责拆成 1 个页面 + 2 个 Hook + 4 个分区组件 + 6 个弹窗：

```
pages/EditorPage.tsx                 (~180)  壳：顶栏/步骤导航/分区切换/任务条
hooks/useEditorData.ts               (~150)  loadAll / 剧集切换 / pipeline-status
hooks/useTaskStream.ts               (~110)  SSE 连接/重连/任务字典/防抖刷新
components/editor/StepNav.tsx        (~60)   5 步导航 + doneMap 三态
components/editor/ScriptTab.tsx      (~200)  剧本编辑、生成、提取角色
components/editor/CharacterTab.tsx   (~260)  角色卡、定妆照、试听
components/editor/BoardTab.tsx       (~420)  分镜卡片、抽卡对比、批量出图/视频
components/editor/VoiceTab.tsx       (~150)  TTS 生成与试听
components/editor/FinalTab.tsx       (~220)  时间线、预检、合成、导出
components/editor/dialogs/*.tsx      (~380)  6 个弹窗
lib/entities.ts                      (~180)  normStoryboard/versionsOf/thumbOf/audioOfSb…
styles/editor.css                    (~900)  样式基本原样复用，仅处理 5 处 .el- 覆盖
```

React 侧总量预计 **2,200–2,400 行**（比原版多约 30%，因为受控组件与显式依赖数组）。

## 六、工期估算

| 阶段 | 内容 | 工作量 |
|---|---|---|
| ① 骨架（已完成） | 类型、实体工具、项目缓存、数据 Hook、SSE Hook、页面壳、路由 | 0.5 天 |
| ② 剧本 + 角色 | `ScriptTab` / `CharacterTab` + 2 个弹窗 | 0.5 天 |
| ③ 画面分镜 | `BoardTab`（含抽卡对比、批量操作）+ 3 个弹窗 | 1–1.5 天 |
| ④ 配音 + 成片 | `VoiceTab` / `FinalTab` + 1 个弹窗 | 0.5 天 |
| ⑤ 联调 | SSE 实测、批量重试、合成导出 | 0.5 天 |

**合计约 3–3.5 人日**，其中真正耗时的是 ③，因为它状态最密（批量选择 + 版本对比 + 6 种操作）。

## 七、迁移顺序建议

1. 先做 `useTaskStream` 并单独验证（起一个出图任务，看进度是否实时推进）——这是唯一有网络实时性的部分，早验证早安心；
2. 再迁 `ScriptTab`（写操作少，验证表单与弹窗模式）；
3. `BoardTab` 放中间，因为它是后续 `FinalTab` 的数据来源；
4. `FinalTab` 涉及 `composite` 长任务，最后做，正好复用 SSE 与任务条。

## 八、残留不确定性

- 原版有若干 `U.*` 容错取值（`asList` / `imgUrlOf` 多字段回落），说明后端返回结构历史上不稳定；React 侧必须逐一保留这些兜底，否则某类项目会空白。
- `pipeline-status` 的 `steps` 结构未在后端 schema 中固化，`doneMap` 做了「后端优先 + 本地兜底」双路推导，移植时不能只取其一。
- 模板中有 5 处 `.el-` 样式覆盖需改写成 antd 选择器，具体在样式移植时逐个处理。