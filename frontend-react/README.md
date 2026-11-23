# AI 漫剧平台 · React 版前端（迁移样板）

Vue 3 + Element Plus 的 `frontend/` 保持不动，本目录是**并列存在**的 React 实现，
用于验证「框架替换 + 组件库替换」是否可行。两套前端共用同一个后端（`/api/v1`，SSE 亦为框架无关）。

## 运行

```bash
pnpm install

# 终端 1：后端（另见 backend/README 或 uvicorn 启动方式）
# 终端 2：
pnpm dev        # http://localhost:5174，/api 与 /static 代理到 localhost:8010
```

Vue 版仍跑在 5173。两个端口是不同 origin，localStorage 天然隔离，
可以同时登录、同时对比，互不干扰。

## 已完成范围（样板）

| 模块 | 状态 | 说明 |
|---|---|---|
| 工程脚手架 | ✅ | Vite 5 + TS 5 + React 18，`@` 别名，端口 5174 |
| 设计令牌 | ✅ | `tokens.css` 从 Vue 版**原样复用**（框架无关） |
| 全局样式 | ✅ | `main.css` 删除 94 条 `.el-*` 覆盖，改由 antd token 承担 |
| 会话与请求层 | ✅ | 单飞刷新、双令牌、设备指纹、401 重放、统一错误归一 |
| 路由与守卫 | ✅ | React Router 7 + `RequireAuth`，`?redirect=` 回跳 |
| 登录页 | ✅ | 左品牌面板 + 胶囊 Tab + 登录表单（字段级错误回显） |
| 注册表单 | ✅ | 五项校验（用户名/密码/确认密码/邮箱/条款）、密码强度条、业务码→字段回显 |
| 找回密码 | ✅ | 三步弹窗（校验用户 → 6 位验证码 + 60s 重发倒计时 → 重置密码），`CODE_EXPIRED` 自动退回第 2 步 |
| 工作台 | ✅ | hero 统计、搜索、状态筛选、项目网格、空状态、骨架 loading |
| 项目卡片 | ✅ | 渐变占位封面、状态胶囊、滚动入场、二次确认删除 |
| 导演工作台（全五个分区） | ✅ | 剧本表格 + 角色卡 + 画面抽卡对比/批量出图出视频 + 配音台本 + 时间线与合成；含 6 个弹窗、SSE 任务条、pipeline 三态推导 |
| 创作页 | ✅ | 灵感输入 + 拖拽导入（.txt/.md/.docx，含手写 ZIP+inflate 解析）、风格卡选择、比例选择、一键流水线 |
| 项目详情 | ✅ | 头部信息与状态标记、剧集卡片网格（智能 CTA + 更多操作）、素材库（图/视频/音频 + 设为封面）、封面生成轮询、两重确认删除 |
| 我的 | ✅ | 资料头部与统计、作品网格、深色模式 / 模型信息 / 改密 / 清除缓存 |
| 风格预设 | ✅ | 列表与「显示已停用」、启停乐观更新 + 回滚、增删改弹窗、名称与提示词校验 |
| 任务进度组件 | ✅ | 摘要胶囊 + `createPortal` 展开面板、进度条、重试/取消、失败聚合 |
| 主题切换 | ✅ | 深/浅双主题，antd `darkAlgorithm` + `data-theme` 双驱动 |

## 迁移完成度

**Vue 版 10,361 行 / 29 个源文件已全部迁移完毕**（React 侧 56 个文件 / 11,746 行），无遗留占位页。
`Editor.vue`（2,686 行）的迁移可行性与拆分方案见 `docs/editor-migration-assessment.md`，五个分区、6 个弹窗与 SSE 任务流均已落地。

## 路由懒加载

Editor（234 KB）、ProjectDetail（50 KB）、Create、Mine、Styles 均已拆为独立 chunk，
首屏只加载主包 + 工作台。下表为 `pnpm build` 实测（gzip）：

| chunk | 体积（gzip） |
|---|---|
| 主包 `index` | 274.8 KB（未压缩 841.9 KB，构建会提示 >500 KB 警告） |
| `EditorPage`（按需） | 76.2 KB |
| `ProjectDetail`（按需） | 17.3 KB |
| `Create` / `Mine` / `Styles`（按需） | 3.9 / 3.2 / 3.1 KB |

## 验证状态

- `pnpm typecheck`：通过
- `pnpm test`：25 个用例通过（页面渲染冒烟 + 数据层/拦截器 + docx 解析）
- `pnpm build`：通过；主包因 antd 全量引入偏大，仍有优化空间
- **前后端联调**：后端 8010 + React 版 5174 实跑，走 vite 代理完成 50 项检查（认证/刷新轮换/401 重放、项目与剧集 CRUD、分镜、角色、风格、任务提交与取消/重试约束、SSE 建连与事件、错误体结构），全部通过

## 联调发现

- 列表接口（`/projects`、`/styles`、`/characters`、`/storyboards`）实际返回 `{items, total}`，前端 `asList` 的 `items` 兜底生效；若后端改为只返 `{projects:[]}` 需同步更新解析 keys。
- `pipeline-status` 的 `script`/`character`/`board` 步骤只有 `count` 字段，而 `stepCount()` 只认 `completed`/`total`，因此这三步的进度计数不显示（`board` 取 `image` 步骤故正常）。Vue 版逻辑相同，属两版共有的既有行为。
- 删除「正在生成封面的项目」时，后端 worker 原会抛 `StaleDataError` + `PendingRollbackError`（`task_engine.py` 的 `update_progress` 与异常处理路径），任务卡在中间态。属后端竞态，已在 `backend/app/services/task_engine.py` 修复：新增 `TaskGone` 与行存在性探测，handler 内行消失即优雅终止；异常处理先 `rollback()` 再重新取对象写终态，避免二次异常。配套 5 个回归用例见 `backend/app/tests/test_task_race.py`，后端全套 62 个测试通过，真实 MySQL 竞态复现已无异常堆栈。
- 上轮 review 修复的 401 分支经联调补充：refresh 已过期（`NO_REFRESH`）时也需清会话，否则用户卡在 401 不跳登录页；已补回归测试。

## 关键迁移决策（面试可讲点）

1. **样式作用域**：Vue 的 `<style scoped>` 改成「父选择器作用域」
   （`.auth-left .logo` / `.auth-card .tab`）。没有引入 CSS Modules，
   因为类名冲突只发生在 `.logo`/`.title` 这类通用名上，父选择器已足够，
   且能让 CSS 与 Vue 版逐行对应，方便回归比对。
2. **状态管理**：Pinia 的 4 个 store 收敛为 3 个 zustand store。
   Vue 版为规避 `request → store → request` 循环依赖，
   不得不用「模块级 ref + store」双载体（`session.js` + `stores/auth.js`）；
   zustand 的 `getState()` 支持组件外读写，**一套载体即够**，循环依赖问题消失。
3. **CSS-in-JS 主题桥接**：Element Plus 靠 CSS 变量吃主题，antd v5 靠 ConfigProvider token。
   `RootProviders` 把 `tokens.css` 的语义色一一映射成 antd token，
   并保留 `data-theme` 给自有 CSS 用，实现两套样式体系共存。
4. **组件库 API 差异**（迁移成本最集中的地方）：
   - `v-model` → 受控组件 `value` + `onChange`
   - `el-form` `validate()` → antd `form.validateFields()`；后端 `field_errors` → `form.setFields()`
   - `ElMessage.error()` → `App.useApp().message`（经 `lib/feedback.ts` 注册，非组件代码也能用主题化提示）
   - `ElMessageBox.prompt`（带输入框的两步确认）→ `Modal.confirm` + 受控 `Modal`
   - `v-loading` → `<Spin>`
   - `v-reveal` 指令 → `useReveal` Hook（共享同一个 IntersectionObserver 实例）
   - `<Transition mode="out-in">` → `key` 重挂载 + CSS 入场动画

## 已知差异

- 视觉非像素级还原：antd 的圆角/间距基线不同于 Element Plus，快捷按钮保留了胶囊形态但内边距有差异。
- React 18 + antd v5；如需 React 19，额外安装 `@ant-design/v5-patch-for-react-19`。
- 同域部署时两版共用登录态会互相踢下线，见下方「并行期注意」。

## 并行期注意

两版沿用同一套存储键（`auth.access` / `auth.refresh` / `auth.remember`）。
**开发期端口不同、天然隔离；上线同域部署时会共享登录态**，
而后端是 refresh rotation（使用即吊销），会导致两个前端互相踢下线。
并行期请只让一个前端对外提供服务，或给 React 版加键名命名空间。