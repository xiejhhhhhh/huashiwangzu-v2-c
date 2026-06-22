# codemap — code map service

codemap 是常驻代码索引模块，给 Agent 提供影响面、边界检查、文件锁和索引可信度反馈。它是运行时能力；本仓同时有 `.codegraph/`，查代码优先用 CodeGraph，codemap 用于后端可用时的模块边界和经验反馈。

## 功能

| 功能 | 说明 |
|---|---|
| 代码索引 | 扫描 `backend/app`、`frontend/src`、`modules`，记录文件、符号、import、call、能力注册/调用、表访问 |
| 影响面 | 查询改某文件会影响哪些文件、模块、能力和表 |
| 边界检查 | 按模块边界规则检查跨模块 import、框架表访问、业务表前缀等 |
| 文件锁 | 多 Agent 并行改文件前可 acquire/check/release 持久化锁 |
| 反馈 | Agent 实读发现 codemap 不准时写入 `codemap_feedback`，用于后续维修 |

## 如何调用

HTTP 前缀：`/api/codemap`，除 rebuild/feedback 管理接口外一般 `viewer` 可用。

| 端点 | 方法 | 用途 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/stats` | GET | 索引规模、confidence、empirical_accuracy |
| `/get-file` | POST | 查询单文件依赖、被依赖、能力、表、stale |
| `/impact` | POST | 查询影响面 |
| `/check-boundary` | POST | 边界合规检查 |
| `/module-map` | POST | 模块能力和边界概览 |
| `/search` | POST | 关键词搜索 |
| `/rebuild` | POST | 全量重建，需 admin |
| `/acquire-lock` | POST | 获取文件锁 |
| `/check-lock` | POST | 检查文件锁 |
| `/release-lock` | POST | 释放文件锁 |
| `/list-locks` | GET | 列活跃锁 |
| `/report-inaccuracy` | POST | 记录索引不准反馈 |
| `/list-feedback` | GET | 查看反馈，需 admin |

跨模块能力与 HTTP 基本一一对应：`codemap:get_file`、`impact`、`check_boundary`、`module_map`、`search`、`stats`、`rebuild`、`acquire_lock`、`check_lock`、`release_lock`、`list_locks`、`report_inaccuracy`、`list_feedback`。

## 示例

```bash
PORT=$(cat backend/logs/.backend.port 2>/dev/null || echo 33000)

curl -sS -X POST "http://127.0.0.1:$PORT/api/codemap/impact" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"path":"modules/agent/backend/router.py"}'
```

## 数据与运行

| 项 | 说明 |
|---|---|
| 数据目录 | `modules/codemap/data/`，已 gitignore |
| 表 | `codemap_feedback` |
| 依赖 | `tree-sitter`、`watchdog` |
| 热更新 | 后端启动后后台建索引，watchdog 500ms 防抖增量更新 |
| 可信度 | `confidence` 是解析覆盖率，`empirical_accuracy` 是反馈后的实战命中率 |

## 边界

- 不索引第三方库、构建产物、sandbox、tests、venv、node_modules。
- 查询返回 `stale` 或 `reliability_note` 时，必须实读文件确认。
- 发现不准后调用 `report_inaccuracy`，不要只在对话里抱怨。

## 验证

```bash
cd backend && .venv/bin/python -m pytest ../modules/codemap/tests/ -v
```
