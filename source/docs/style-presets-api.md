# 风格预设（Style Presets）API 文档

> Base URL: `http://localhost:8010/api/v1` · 认证: `Authorization: Bearer <JWT>`（除 auth 外全部端点强制鉴权）
> 数据模型: MySQL 表 `style_presets`（`backend/app/models.py` StylePreset）

## 对象结构 StylePreset

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | int | 主键 |
| `user_id` | int | 归属用户（自动填充，数据隔离） |
| `name` | string(64) | 风格名称，**同用户内唯一** |
| `prompt` | text | 正向提示词（英文关键词，用于 AI 出图） |
| `description` | string(256)? | 简介（前端展示用） |
| `negative_prompt` | text? | 负向提示词 |
| `color` | string(32)? | 展示色（可选） |
| `is_active` | bool | 启用/停用（停用项不出现在创作页选项） |
| `sort_order` | int | 排序权重（升序） |
| `created_at` / `updated_at` | ISO datetime | 时间戳 |

## 端点

### GET /styles — 列表（分页 + 懒 seed）

```
GET /api/v1/styles?page=1&page_size=20&include_inactive=false
```
- `page ≥ 1`，`page_size 1..100`，`include_inactive` 默认 false（仅启用项）
- 排序 `sort_order asc, id asc`
- **懒 seed**：该用户首次访问且无任何预设时自动写入 6 条默认风格（赛博朋克/水墨国风/日系动漫/美式漫画/3D卡通/写实）

```json
{ "items": [ { "id": 1, "name": "赛博朋克", "...": "..." } ], "total": 6 }
```

### POST /styles — 创建

```json
{ "name": "蒸汽朋克", "prompt": "steampunk, brass, victorian", "description": "黄铜与齿轮", "negative_prompt": "modern", "is_active": true, "sort_order": 10 }
```
- 校验：`name` 必填 1-64、`prompt` 必填 ≤2000、`description` ≤256、`negative_prompt` ≤2000、`color` ≤32
- 重名 → `400 {"code":400,"message":"风格名称已存在"}`
- 成功返回完整对象

### GET /styles/{id} — 详情
- 不存在或非本人 → `404`

### PUT /styles/{id} — 更新（部分字段）
- 仅提交的字段被更新（`exclude_unset`）；改名撞已有名称 → `400`

### PATCH /styles/{id}/toggle — 启停切换
- 返回切换后的完整对象（`is_active` 取反）

### DELETE /styles/{id} — 删除（硬删除）
- 成功返回 `{"ok": true, "message": "风格已删除"}`

## 错误约定

| 状态码 | 场景 |
|---|---|
| 401 | 未携带/无效 token（`{"code":401,"message":"..."}`） |
| 404 | 预设不存在或不属于当前用户（统一 404 避免探测） |
| 400 | 名称重复 / 字段校验失败 |
| 422 | Pydantic 请求体校验失败 |

## 与生成链路的集成

`backend/app/services/task_engine.py` `_build_image_prompt()`：按 `project.user_id + project.style` 匹配**启用中**的预设，命中则用 `preset.prompt` 替换裸风格名并追加 `negative_prompt`；未命中（历史项目/自定义文本）行为不变。

## 快速示例（curl）

```bash
# 登录取 token
curl -s -X POST http://localhost:8010/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"u1","password":"p1"}'
# 列表
curl -s http://localhost:8010/api/v1/styles -H "Authorization: Bearer $TOKEN"
# 创建
curl -s -X POST http://localhost:8010/api/v1/styles -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name":"水墨写意","prompt":"ink wash painting, freehand"}'
# 停用
curl -s -X PATCH http://localhost:8010/api/v1/styles/7/toggle -H "Authorization: Bearer $TOKEN"
# 删除
curl -s -X DELETE http://localhost:8010/api/v1/styles/7 -H "Authorization: Bearer $TOKEN"
```
