# AI 漫剧智能制作平台

基于多模态大模型的 AI 漫剧（漫画短剧）创作平台：从剧本到分镜、角色、镜头、视频合成，一条流水线完成整集漫剧的生产。

后端 FastAPI 负责项目/剧集/分镜数据与 AI 任务调度，前端 Vue 3 提供工作台、创作与编辑界面，AI 能力由 Agnes AI（文本/图像/视频）与阿里云 DashScope（TTS）提供，FFmpeg 负责音视频合成。

[![tests](https://github.com/zhizhnagertong/AI-drama/actions/workflows/tests.yml/badge.svg)](https://github.com/zhizhnagertong/AI-drama/actions/workflows/tests.yml)

![四层架构](figures/architecture-4layers.png)

## 功能概览

| 模块 | 说明 |
|---|---|
| 账号体系 | 注册 / 登录 / 找回密码，JWT 双令牌（access + refresh），登录失败锁定 |
| 工作台 | 项目列表、进度总览、任务队列 |
| 创作流程 | 剧本 → 剧集 → 分镜（storyboard）→ 角色（character）→ 镜头（shot）→ 时间线（timeline） |
| 风格预设 | 内置漫剧风格模板，支持自定义并应用到项目 |
| AI 任务 | 异步任务引擎 + SSE 实时推送进度，失败可重试 |
| 视频合成 | FFmpeg 合成画面与 TTS 配音，产物落在 `backend/storage`，通过 `/static` 对外提供 |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 / Pydantic v2 / Uvicorn |
| 数据库 | MySQL 8（`utf8mb4`），启动时自动建库建表 |
| AI | Agnes AI（文本、图像、视频）、DashScope TTS、DeepAgents 编排 |
| 媒体 | FFmpeg（由 `imageio-ffmpeg` 提供可执行文件） |
| 前端（主） | Vue 3 / Element Plus / Pinia / Vue Router / Vite 5 |
| 前端（React 版） | React 18 / antd 5 / Zustand / React Router 7 / Vite 5 / Vitest |

## 目录结构

```
drama/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口，/health、/static 挂载
│   │   ├── core/              # 配置(config.py)、数据库(db.py)、鉴权(security.py)
│   │   ├── api/               # 路由：auth / projects / episodes / storyboards /
│   │   │                      #       characters / shots / tasks / timelines / sse
│   │   ├── models.py          # SQLAlchemy ORM 模型
│   │   ├── schemas.py         # Pydantic 请求响应模型
│   │   ├── services/          # 任务引擎、事件总线、合成器、AI Provider、存储
│   │   └── tests/             # pytest 测试与验证脚本
│   ├── migrations/            # 增量 SQL 迁移（建表由 ORM 自动完成）
│   ├── requirements.txt
│   └── .env.example           # 配置模板，需复制为 .env
├── frontend/                  # Vue 3 版前端（start.ps1 启动的就是它）
├── frontend-react/            # React 版前端（并行重写版本，见其 README）
├── docs/                      # 模块设计与测试报告
├── figures/                   # 架构图与需求图
├── PRD.md                     # 产品需求文档
├── start.ps1                  # 一键启动（自动装依赖）
└── stop.ps1                   # 一键停止
```

## 快速开始

### 1. 环境要求

- Python **3.10+**
- Node.js **18+**（Vue 版用 npm / React 版用 pnpm；**pnpm 11 需 Node ≥ 22.13**，CI 使用 Node 22）
- MySQL **8.x**，已启动并知道 root 密码
- Windows PowerShell 5.1+（`start.ps1` 依赖 PowerShell）

### 2. 克隆

```bash
git clone git@github.com:zhizhnagertong/AI-drama.git
cd AI-drama
```

### 3. 配置 `backend/.env`（**必做**，此文件不入库）

```powershell
Copy-Item backend\.env.example backend\.env
```

然后填写：

| 变量 | 必填 | 说明 |
|---|---|---|
| `DB_HOST` / `DB_PORT` | 否 | 默认 `localhost:3306` |
| `DB_USER` / `DB_PASSWORD` | **是** | 你本机 MySQL 的账号密码 |
| `DB_NAME` | 否 | 默认 `ai_manga_studio2`，**库不存在会自动创建** |
| `AGNES_API_KEY` | AI 功能必填 | Agnes AI 密钥，文本/图像/视频生成依赖它 |
| `AGNES_TEXT_MODEL` / `AGNES_IMAGE_MODEL` / `AGNES_VIDEO_MODEL` | 否 | 模型名，不填用内置默认值（`agnes-2.5-flash` / `agnes-image-2.1-flash` / `agnes-video-2.5-flash`），**换模型只改这里** |
| `DASHSCOPE_API_KEY` | TTS 必填 | 留空时语音合成相关接口返回 400 |
| `JWT_SECRET` | 建议改 | 生产环境务必替换为随机串 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | access token 有效期，默认 15 分钟 |
| `LOG_RESET_CODE` | 否 | 本地调试设为 `true` 才会把找回密码验证码打到日志，**生产必须保持 false** |
| `STORAGE_DIR` | 否 | 产物目录，默认 `backend/storage` |

> 没填 AI Key 也能启动，界面与数据流程可用，只是 AI 生成类任务会失败。

### 4. 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本会自动完成：创建 `backend/.venv` → 安装 Python 依赖（清华镜像）→ `npm install`（npmmirror）→ 启动前后端 → 健康检查。

停止：

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

### 5. 访问

| 地址 | 说明 |
|---|---|
| http://localhost:5173 | 前端（Vue 版） |
| http://localhost:8010/health | 后端健康检查 |
| http://localhost:8010/docs | Swagger API 文档 |

### 手动启动（可选）

```powershell
# 后端
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

前端 `vite.config.js` 已把 `/api` 与 `/static` 反代到 `localhost:8010`，无需额外配置接口地址。

## AI 模型配置

所有 AI 相关配置都在 **`backend/.env`** —— 该文件不入库（含密钥），由 `backend/.env.example` 复制而来；Docker 部署时改在仓库根目录的 `.env` 里（compose 会把它注入容器环境变量）。

### 1. 密钥与接口地址

| 变量 | 默认值 | 是否必填 | 说明 |
|---|---|---|---|
| `AGNES_API_KEY` | 空 | **AI 功能必填** | Agnes AI 密钥，文本 / 图像 / 视频统一使用 |
| `AGNES_BASE_URL` | `https://apihub.agnes-ai.com` | 否 | 文本与图像接口地址 |
| `AGNES_VIDEO_BASE_URL` | `https://api.agnes-ai.cn` | 否 | 视频接口地址（与文本/图像不同域名） |
| `DASHSCOPE_API_KEY` | 空 | 配音功能必填 | 阿里云百炼 Key；留空时「角色试音」「分镜配音」返回 400 |

### 2. 模型名

| 变量 | 默认值 | 影响功能 |
|---|---|---|
| `AGNES_TEXT_MODEL` | `agnes-2.5-flash` | 剧本生成、角色提取、分镜拆分 |
| `AGNES_IMAGE_MODEL` | `agnes-image-2.1-flash` | 分镜出图、角色定妆照、项目封面 |
| `AGNES_VIDEO_MODEL` | `agnes-video-2.5-flash` | 图生视频（参考图 → 视频） |

**换模型只改这三行，不需要改代码**；留空则使用上表默认值。

TTS 模型无需配置：程序按音色后缀自动选择 `cosyvoice-v2`（音色名以 `_v2` 结尾）或 `cosyvoice-v1`。

### 3. 生效方式

```powershell
# 本地脚本部署
powershell -ExecutionPolicy Bypass -File .\stop.ps1
# 编辑 backend\.env 后重启
powershell -ExecutionPolicy Bypass -File .\start.ps1

# Docker 部署
docker compose restart backend
```

改完必须重启后端——配置在进程启动时读取并缓存。启动日志若出现「未找到 backend/.env」，说明配置文件还没创建。

### 4. 未配置时的表现

- 应用**照常启动**，登录、项目管理、分镜编辑、时间线等非 AI 功能全部可用
- 触发 AI 生成的任务会失败，原因写入任务的 `error` 字段（前端任务卡片可见）和 `backend/uvicorn.log`
- 缺少 `DASHSCOPE_API_KEY` 时仅影响语音合成，其他 AI 功能不受影响

## 使用 Docker 部署

无需在本机安装 Python / Node / MySQL，只要能跑 Docker 即可。

```bash
# 1. 准备密钥（可选；不填也能启动，但 AI 功能不可用）
#    在仓库根目录创建 .env（该文件已被 .gitignore 忽略）
cat > .env <<'EOF'
DB_PASSWORD=root
JWT_SECRET=change-me-to-a-random-string
AGNES_API_KEY=
DASHSCOPE_API_KEY=
# 模型名（可留空使用默认值）
AGNES_TEXT_MODEL=agnes-2.5-flash
AGNES_IMAGE_MODEL=agnes-image-2.1-flash
AGNES_VIDEO_MODEL=agnes-video-2.5-flash
EOF

# 2. 构建并启动（前端 + 后端 + MySQL 三个容器）
docker compose up -d --build

# 3. 查看状态与日志
docker compose ps
docker compose logs -f backend

# 4. 停止 / 销毁
docker compose down          # 保留数据卷
docker compose down -v       # 连同数据库与产物一起删除
```

启动后访问：

| 地址 | 说明 |
|---|---|
| http://localhost:5173 | 前端（Nginx 托管构建产物，`/api` 与 `/static` 反代到后端） |
| http://localhost:8010/health | 后端健康检查 |
| http://localhost:8010/docs | Swagger API 文档 |
| localhost:3307 | MySQL（宿主机端口，避免与本机 3306 冲突） |

编排文件 [docker-compose.yml](docker-compose.yml) 的要点：

- **依赖顺序**：`mysql` 健康检查通过后才启动 `backend`，`backend` 健康后才启动 `frontend`
- **数据库自动初始化**：后端启动时自动 `CREATE DATABASE` 并建表，无需手工导入
- **数据持久化**：`mysql_data` 卷存数据库，`backend_storage` 卷存分镜图/成片等产物
- **配置注入**：全部通过环境变量传入，容器内不落地 `.env` 文件
- **端口可改**：`BACKEND_HOST_PORT`、`FRONTEND_HOST_PORT`、`MYSQL_HOST_PORT` 三个变量可覆盖宿主端口
- **镜像**：后端 `python:3.12-slim`，前端 `node:20-alpine` 构建 + `nginx:alpine` 运行，MySQL 8.0

手动构建单个镜像：

```bash
docker build -t drama-backend ./backend
docker build -t drama-frontend ./frontend
```

## React 版前端

`frontend-react/` 是并行的 React 重写版本，与 Vue 版共用同一后端（同样反代 8010）：

```bash
cd frontend-react
pnpm install
pnpm dev        # 端口与 Vue 版冲突时先停掉 Vue 版
pnpm test       # Vitest
pnpm build      # tsc --noEmit && vite build
```

## API 一览

统一前缀 `/api/v1`，完整定义见 `/docs`：

| 前缀 | 模块 |
|---|---|
| `/auth` | 注册、登录、刷新令牌、找回密码 |
| `/projects` | 项目 CRUD、封面 |
| `/episodes` · `/storyboards` · `/characters` · `/shots` · `/timelines` | 创作流水线各环节 |
| `/styles` | 风格预设 |
| `/tasks` | 任务提交、查询、重试 |
| `SSE` | 任务进度实时推送 |

## 测试

```bash
# 后端（需可用的 MySQL）
cd backend
.\.venv\Scripts\python.exe -m pytest app/tests

# React 前端
cd frontend-react
pnpm test
```

## 常见问题

**`git clone` 报 `Connection was reset`**
本机到 `https://github.com` 的连接可能被重置，改用 SSH（`git@github.com:...`，需已配置 SSH Key），或先配好代理（`git config --global http.proxy http://127.0.0.1:7890`）。

**启动后 8010 端口报数据库连接错误**
检查 MySQL 是否启动、`backend/.env` 中的用户名密码是否正确。数据库和表由 `init_db()` 在启动时自动创建，无需手工执行 SQL。

**依赖安装很慢或失败**
`start.ps1` 已使用国内镜像（pypi 清华源、npm npmmirror）。若仍失败，删掉 `backend/.venv` 或 `frontend/node_modules` 后重试。

**端口被占用**
后端固定 8010、前端 5173。先运行 `stop.ps1`，或修改 `start.ps1` 中的端口与 `frontend/vite.config.js`。

**AI 生成任务失败**
确认 `AGNES_API_KEY` / `DASHSCOPE_API_KEY` 已填且额度充足；查看 `backend/uvicorn.log` 与 `backend/uvicorn.err.log`。

## 相关文档

- [产品需求文档 PRD.md](PRD.md)
- [剧集模块设计](docs/episodes-module.md)
- [风格预设 API](docs/style-presets-api.md) · [风格预设 UI](docs/style-presets-ui.md) · [风格预设测试报告](docs/style-presets-test-report.md)
- [模型选型说明](Agnes%20AI%20模型选择.md)