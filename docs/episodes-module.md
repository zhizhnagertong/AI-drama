# 多集管理模块（项目 → 剧集 → 分镜）实施说明与后续建议

> 参考项目：[chatfire-AI/huobao-drama](https://github.com/chatfire-AI/huobao-drama)
> 实施日期：2026-09-08
> 状态：已完成并通过验证（后端 33 项测试 + 真实 MySQL 冒烟 + 前端构建）
> 同日追加：工作台优化（见第五节，5.1~5.4/5.6/批次 A.1/C.8/C.9 已实施）

## 一、本次已实现的内容

对齐 huobao-drama 的 `drama → episodes → storyboards` 三层结构，在现有
`project → storyboards` 两层模型上做**增量扩展**，不破坏任何已有链路与存量数据。

### 1. 数据模型（`backend/app/models.py`）

- 新增 `Episode` 表（`episodes`）：
  - `project_id` / `episode_number`（集号）/ `title` / `synopsis`（梗概）/ `inspiration`
  - `status`（`EpisodeStatus`：draft → script_ready → producing → completed / failed）
  - **配置快照**：`style` / `aspect_ratio` / `voice_config` 建集时从项目固化，
    之后项目改动不影响历史集（借鉴 huobao 建集锁定 image/video_config_id 的思想）
  - `deleted` 软删除，与 Project 一致
- `Storyboard`、`Timeline` 各加可空 `episode_id` 外键（索引）。
  可空设计 = 存量数据零迁移成本，由启动回填自动补齐。

### 2. 启动迁移与存量回填（`backend/app/core/db.py`）

`init_db()` 在 `create_all` 之后追加两步（幂等，每次启动重放）：

- `_ensure_columns`：查 `information_schema` 给旧表补 `episode_id` 列；
- `_backfill_episodes`：为没有任何集的未删项目创建"第1集"（继承项目状态与配置），
  并把其下 `episode_id IS NULL` 的分镜/时间线归入该集。

实测：22 个存量活跃项目全部回填成功；34 个"孤儿分镜"均属于已软删项目，符合预期。

### 3. 后端接口（`backend/app/api/routes_episodes.py`，前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/projects/{pid}/episodes` | 集列表（含每集 stats：分镜/镜头/已出图/视频/是否有成片） |
| POST | `/projects/{pid}/episodes` | 新增一集：集号 = max(未删)+1，锁定配置快照 |
| GET | `/episodes/{id}` | 集详情 + 该集分镜 + 该集时间线 |
| PUT | `/episodes/{id}` | 改标题/梗概/灵感/状态（非法状态 400） |
| DELETE | `/episodes/{id}` | 软删；**项目仅剩一集时禁止删除**（400） |
| POST | `/episodes/{id}/generate-script` | 按集生成剧本（只重建该集分镜） |
| POST | `/episodes/{id}/pipeline` | 按集一键流水线 |
| POST | `/episodes/{id}/storyboards` | 该集下手动加一幕 |
| GET | `/episodes/{id}/storyboards` | 该集分镜列表 |
| GET | `/episodes/{id}/export` | 该集成片导出 |

向后兼容：

- `POST /projects/{pid}/generate-script` 与 `/pipeline` 自动路由到**默认集**
  （最小集号；默认集被软删后自动顺延），老前端/脚本无感知；
- 项目详情 `GET /projects/{pid}` 响应新增 `episodes` 字段；
- 任务仍挂在 `project_id` 上，SSE 流、任务列表接口全部不变；
- 时间线创建支持 `episode_id`（缺省回退默认集），导出支持 `?episode_id=` 过滤。

### 4. 任务引擎（`backend/app/services/task_engine.py`）

`_handle_script` 升级：

- `payload.episode_id` 存在 → 只删除并重建**该集**分镜（多集互不干扰）；
- 新分镜写入 `episode_id`；集状态推进（script_ready / producing）、
  `logline` 回写、默认标题自动替换为 AI 生成的剧名；
- 缺省回退默认集，极端情况下（无任何集）仍可工作（episode_id=NULL）。

### 5. 前端

- **ProjectDetail.vue**：新增「剧集」Tab（默认页）——集卡片显示集号/标题/梗概/
  分镜数/视频数/成片标记，操作含进入工作台、生成剧本、一键流水线、编辑、删除；
  头部 meta 显示"N 集"。原「分镜」板块已按需求移除
  （2026-09-08 后续调整，页面现仅保留「剧集」+「素材库」两个 Tab，分镜编辑统一在工作台进行）。
- **Editor.vue**：顶栏新增**集切换器**（`?episode=` 深链支持从详情页直达指定集）；
  分镜/时间线按当前集过滤；剧本生成、时间线构建、成片导出均携带当前集。
  角色保持项目级共享（定妆照跨集复用，这正是多集的核心收益）。

### 6. 测试

- `backend/app/tests/test_episodes.py`：18 项（内存 SQLite），覆盖模型字段、
  真实 `_backfill_episodes` 幂等性、集 CRUD、集号分配、配置快照、跨用户 404、
  按集剧本 handler（含 pipeline 与无集回退）、分镜按集、时间线按集、级联删除。
- `backend/app/tests/verify_episodes.py`：对运行中服务的 9 步真实 MySQL 冒烟。
- 原有 `test_styles.py` 9 项全部通过，无回归。

## 二、设计决策与取舍

| 决策 | 理由 |
|---|---|
| `episode_id` 可空而非必填 | 存量数据免迁移；回填失败也不会让现有流程报错 |
| 任务仍挂 project_id | SSE 通道、任务列表、重试逻辑零改动；集归属走 payload |
| 角色留在项目级 | 定妆照/音色是 IP 资产，跨集复用正是多集的价值 |
| 集软删但分镜保留 | 与 huobao 一致："保留但不可达"，防误删且可追溯 |
| 配置快照只存 style/比例/配音 | 当前单供应商（Agnes），config_id 快照待配置入库后再加 |
| 最后一集禁止删除 | 项目至少保留一集，避免空壳项目 |

## 三、尚未实施（建议后续按序推进）

以下来自同一份对比分析，本次有意未做，按性价比排序：

### 批次 A：低成本修缺陷（建议下一个迭代做）

1. **项目状态手动标记**：卡片角标可点击切 draft/active/completed（乐观更新），
   顺带解决 `ProjectStatus.completed` 无写入路径的问题；成片导出成功时自动置 completed 兜底。
   > ✅ 已实施（2026-09-08）：ProjectDetail 头部状态标签可点击弹出菜单切换 5 种状态
   > （乐观更新 + 失败回滚），后端 `PUT /projects/{id}` 接受 `status` 并校验合法性；
   > 集卡片主按钮改为智能 CTA（开始制作/继续制作/查看成片）。
   > 待办：导出成功自动置 completed 的兜底、Workspace 卡片角标同款交互。
2. **列表接口带 stats + 封面**：`GET /projects` 附带集数/分镜数/封面缩略图 URL；
   前端把 keyword/status/排序参数真正传给后端（当前全在前端本地过滤）。
3. **`GET /projects/stats`** 全局聚合端点，替代前端拉 100 条自算。

### 批次 B：性能与卫生

4. **缩略图管线**：落盘时 Pillow 产出 400px webp + 视频抽帧 poster；
   一次性 backfill 脚本补齐存量（storage 已 330MB+ 原图直出）。
5. **磁盘 GC**：软删超 N 天的项目文件物理清理 + 孤儿文件扫描。
6. **任务队列持久化**：进程重启后 queued/running 任务成孤儿，
   启动时扫描 running/queued 重新入队（或标记 failed 可重试）。

### 批次 C：配置与多集增强

7. **API 配置入库 + 设置页**：`ai_service_configs` 表 + 连通性测试 +
   未配置横幅引导；改 key 不再重启后端。届时补上集级 config_id 快照。
8. **流水线状态下沉后端**：`GET /episodes/{id}/pipeline-status` 返回 6 环节
   done/partial/pending，替代 Editor.vue 前端推导。
   > ✅ 已实施（2026-09-08，随 5.2 完成）。
9. **批量生成前确认**：镜头数 × 版本数 × 模型的成本预览弹窗；失败任务聚合一键重试。
   > ✅ 已实施（2026-09-08，随 5.4 完成）。
10. **集内资产关联**（远期）：storyboard ↔ character 多对多，
    替代当前"文本里匹配角色名"的脆弱逻辑。

### 明确不建议做

- 迁移 Mastra/TS 技术栈（现有 Python 引擎已跑通全流程）；
- 道具(props)系统、分镜 angle/movement 细粒度字段（投入产出比低）；
- 项目复制/归档（等批次 A 完成后再评估需求强度）。

## 四、遗留小问题（本次已知但未修）

- Editor.vue 分镜 Tab 的 reorder 仍走项目级接口
  （前端只传当前集 id，后端按传入顺序重编 seq，行为正确但语义上可加 `/episodes/{id}/storyboards/reorder`）；
- 工作台卡片封面/统计在列表接口补 stats 前仍显示不全（批次 A.2 解决）；
- `_backfill_episodes` 对"有分镜但项目已软删"的历史数据不做处理（设计如此，
  软删项目本就不可达；若未来加"回收站/恢复"功能需一并回填）。

## 五、创作工作台（Editor.vue）对比与优化建议

> 追加于 2026-09-08。**实施状态（同日）：5.1~5.4、5.6 已实施并通过验证**
> （后端 24 项 pytest + 真实 MySQL 8 步冒烟 `verify_workbench.py` + 前端构建）；
> 5.5 @提及参考图依赖批次 C.10 结构化关联暂缓；5.7 批量配音按钮未做。详见各小节标注。

### 5.1 顶栏：缺"导航感" —— ✅ 已实施（模型选择器除外）

| huobao 有 | 本项目现状 | 差距 |
|---|---|---|
| 流水线进度 pill（当前环节 + `N/M`） | 仅显示"第几步/共 6 步" | 看不出"卡在哪、完成了多少" |
| 智能主 CTA：`开始制作 / 继续制作 / 查看成片` 一键跳到该去的面板 | 无 | 用户每集进来都要自己点侧栏 |
| 任务抽屉按钮 + 活跃任务数角标 | TaskProgress 小组件 | 任务多时看不全、无历史 |
| 文本/图片/视频/分辨率 4 个模型选择器 | 无（模型硬编码 Agnes） | 依赖批次 C 配置入库，现在做没意义 |

**建议**：① 顶栏进度 pill（如 `画面 8/10 · 进行中`）；② 智能 CTA 按钮，
按 `doneMap` 推导跳到第一个未完成步骤，有成片则变"查看成片"。两个纯前端，成本低。

> ✅ 已实施：顶栏新增流水线进度 pill（`done 环节数/6`）、智能 CTA
> （`开始制作/继续制作/查看成片`，一键跳到首个未完成步骤）、活跃任务数角标、
> 失败任务「重试失败(N)」聚合按钮。模型选择器仍待批次 C.7。

### 5.2 左侧流水线：只有"完成/未完成"两态

huobao 每个环节有 `done / active（脉冲动画 + "进行中"标签）/ pending` 三态，
状态由后端 `pipeline-status` 统一计算。本项目 `doneMap` 前端推导、无"进行中"态——
出图跑到一半侧栏毫无感知。

**建议**：与批次 C.8（`GET /episodes/{id}/pipeline-status`）一起做，
侧栏加 active 脉冲态 + 每环节计数（如"画面 8/10"）。

> ✅ 已实施：后端新增 `GET /episodes/{id}/pipeline-status`（6 环节 done/partial/pending + 计数）；
> 侧栏三态（done 打勾 / active 橙色脉冲 + "进行中" / pending），环节名旁显示 `8/10` 计数徽标。

### 5.3 剧本环节：最实质的功能缺口

huobao 把剧本拆成两步：**原始内容（可编辑 textarea + 字数统计）→ AI 改写（可跳过/重新改写）**，
格式化剧本本身可保存可手改，资产提取基于改后剧本单独触发。

本项目链路是"一键生成 → 直接落成 6-10 条分镜表"，两个痛点：

1. 对剧本整体不满意只能重新生成，而重新生成会**删光该集全部分镜和已抽的卡**
   （`_handle_script` 重建逻辑）；
2. 角色提取和分镜提取绑死在一次生成里，不能"只重提角色、保留分镜"。

**建议**：剧本 Tab 顶部加"剧本全文"视图（logline + 剧情梗概可编辑，
存到 `episode.synopsis` 或新字段），改完可只重跑分镜拆解；
再加"重新提取角色"独立按钮。防止误删劳动成果的关键改动。

> ✅ 已实施：剧本 Tab 顶部新增「剧本梗概」可编辑卡片（字数统计 + 保存，写 `episode.synopsis`，
> 不影响分镜）；新增「重提角色」按钮（`POST /episodes/{id}/extract-characters`，
> 按现有分镜文本只更新角色、**不删分镜**）；「AI 生成分镜脚本」在已有分镜时弹二次确认，
> 明示"将删除本集全部分镜与画面"。

### 5.4 画面/视频：批量能力是最大差距（优先级最高）—— ✅ 已实施

huobao v3.1.0：

- **批量视频**：勾选多个分镜 → 生成前确认弹窗（镜头数 × 时长 × 模型 × 分辨率 = 成本预览）
  → 提交 → 失败任务聚合一键重试；
- **批量出图**（资产区"批量角色/批量场景"按钮）；
- 分镜时长可在视频参数区直接编辑保存。

本项目**全部是单镜头操作**：10 个分镜要手动点 10 次"生成画面"、再点 10 次"生成视频"，
每次视频轮询最长 10 分钟。这是工作台效率的头号瓶颈。

**建议**：画面 Tab 加选择模式（卡片左上角 checkbox + 全选）→
「批量生成画面」「批量生成视频」→ 确认弹窗显示 `N 镜 × M 版，预计耗时`。
任务引擎天然支持并发（4 worker + 幂等键），只是前端没聚合入口。

> ✅ 已实施：画面 Tab 新增「批量模式」（卡片左上角 checkbox + 全选）→
> `POST /episodes/{id}/batch-images`、`POST /episodes/{id}/batch-videos`；
> 确认弹窗显示 镜数 × 版本数 / 时长 / 模型 / 预计耗时；批量视频自动跳过
> 无选定画面或已有视频的镜头并回报 skipped 数。
> 失败任务顶栏「重试失败(N)」一键聚合重试。

### 5.5 @提及参考图（中期最有质感的功能）—— ⏸ 暂缓（依赖批次 C.10）

huobao 的 `MentionTextarea`：分镜描述里输入 `@` 弹出角色/场景列表
（带头像、分组、键盘导航、高亮镜像层），选中的角色定妆照作为 `reference_image`
传给视频模型——解决"画面里角色和定妆照长得不一样"的一致性顽疾。

本项目的底子够用：出图时已按角色名文本匹配注入 `prompt_template`，
`Asset.meta.remote_url` 已存远程图地址。缺的是**结构化关联**
（storyboard ↔ character 多对多，即批次 C.10）和前端 @ 组件。
做完它成片角色一致性会有明显提升。

### 5.6 成片环节：缺"预检"

huobao 拼接前校验每个镜头视频文件存在，缺失会点名提示；
真人/敏感内容审核失败时提示换模型重试。
本项目 `composite` 直接提交，失败才报错。

**建议**：合成按钮旁加预检清单——"10 镜中 2 镜无视频，是否跳过继续？"
（后端 `_auto_items` 本来就只取有版本的，但用户不知道少了谁）。

> ✅ 已实施：`GET /episodes/{id}/composite-check` 返回缺视频镜头清单；
> 点「合成成片」时若有缺失，弹确认框点名"第 N 幕缺少镜头视频，时间线将自动跳过"。

### 5.7 配音：基本够用

逐幕配音 + 试听 + 音色匹配已对齐。可借鉴小项：配音 Tab 加
"批量生成全部台词配音"按钮（同样走批量确认模式）。

### 5.8 工作台改造优先级汇总

只做三件事的话：

1. **批量出图/出视频 + 成本确认弹窗 + 失败一键重试**（效率，最高优先，对应 5.4）；
2. **剧本可编辑 + 只重提角色不删分镜**（数据安全，对应 5.3）；
3. **三态流水线侧栏 + 顶栏进度 pill + 智能 CTA**（导航感，对应 5.1/5.2）。

中期再排：@提及参考图（5.5）、pipeline-status 后端化（并入批次 C.8）、
合成预检（5.6）。模型选择器（5.1 末行）必须等批次 C.7 配置入库之后再动。
其中 5.4 与批次 C.9（批量生成前确认）是同一件事，合并实施。
