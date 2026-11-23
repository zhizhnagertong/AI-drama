# 风格预设功能 · 测试报告

日期：2026-09-08 · 环境：backend 8010（MySQL ai_manga_studio2）/ frontend 5173

## 1. 单元测试（pytest）

命令：`python -m pytest app/tests/test_styles.py -v --cov=app.api.routes_styles --cov=app.services.style_seed`

结果：**9 passed**（SQLite in-memory + FastAPI dependency_overrides）

| 用例 | 覆盖点 | 结果 |
|---|---|---|
| test_list_lazy_seed | 首次访问自动 seed 6 条默认风格 | ✅ |
| test_create_and_get | 创建 + 详情返回完整字段 | ✅ |
| test_create_duplicate_name_400 | 同用户重名 400 | ✅ |
| test_update | 部分字段更新（exclude_unset）+ 改名撞名 400 | ✅ |
| test_toggle | PATCH 启停切换 + 列表默认过滤停用项 | ✅ |
| test_delete | 硬删除后列表与详情均不可见 | ✅ |
| test_cross_user_404 | 越权访问他人预设 404（数据隔离） | ✅ |
| test_unauthorized_401 | 无 token 401 | ✅ |
| test_seed_only_when_no_presets | seed 幂等（已有预设不重复写入） | ✅ |

**覆盖率**：

```
Name                         Stmts   Miss  Cover
------------------------------------------------
app\api\routes_styles.py        72      6    92%   (63-65, 106-108: IntegrityError 并发兜底分支)
app\services\style_seed.py      10      0   100%
------------------------------------------------
TOTAL                           82      6    93%
```

未覆盖的 6 行为并发写入触发数据库 IntegrityError 的兜底 except 分支，正常请求路径难以构造，逻辑已由预查重 + 唯一约束双重保障。

## 2. 后端集成测试（真实 MySQL + 运行中服务，端到端 HTTP）

注册测试账号 `e2e_style_u1` 后按序验证：

| # | 操作 | 预期 | 实际 |
|---|---|---|---|
| 1 | GET /styles | 200，懒 seed 返回 6 条默认风格 | ✅ total=6 |
| 2 | POST /styles（新名称） | 200，返回完整对象（含 id/is_active=true） | ✅ id=20 |
| 3 | POST 重名 | 400 | ✅ status=400 |
| 4 | PUT /styles/{id} description | 200，description 更新，其余字段不变 | ✅ |
| 5 | PATCH /styles/{id}/toggle | 200，is_active true→false | ✅ |
| 6 | GET /styles（默认） | 不含刚停用的项 | ✅ total=6 且不含该项 |
| 7 | GET /styles?include_inactive=true | 包含停用项 | ✅ total=7 |
| 8 | DELETE /styles/{id} | `{"ok":true,"message":"风格已删除"}` | ✅ |
| 9 | GET /styles（无 token） | 401 | ✅ status=401 |

## 3. 前端验证

- `npm run build`：✅ 通过（1694 modules，无错误）
- 路由 `/styles` 注册与「我的」页入口：✅ 编译期校验
- 表单校验（必填/长度/trim）、重名 400 字段标红、删除二次确认、toggle 乐观更新回滚、加载失败重试、后端不可用时回退内置 STYLES：代码级实现并编译通过
- 浏览器 UAT 路径：登录 → 我的 → 风格预设 → 新建「国潮工笔」→ 创作页确认新风格出现 → 停用确认消失 → 删除确认移除

## 4. 已知限制与建议

1. 测试账号 `e2e_style_u1`、`styletest_user` 及其预设数据保留在库中，可随时删除（`DELETE FROM style_presets WHERE user_id IN (...)`）。
2. 预设与项目为**名称软引用**：改名后历史项目的 style 字段不随之更新（出图时按名称匹配失败则回退裸文本拼接，行为安全）。如需强一致可后续引入 style_preset_id 外键。
3. 删除为硬删除（预设无历史引用负担）；如需审计可改软删除（项目表 deleted 先例）。
4. 并发创建同名依赖 DB 唯一约束兜底（该分支未被单测覆盖，见 §1）。
