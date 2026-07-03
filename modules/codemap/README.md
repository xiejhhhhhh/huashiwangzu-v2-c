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
| `/stats` | GET | 索引规模、confidence、feedback_count、empirical_accuracy/status/note |
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
| `/list-feedback` | GET | 查看反馈，需 admin；无反馈时返回 `has_feedback:false` 与 `empty_note` |

跨模块能力与 HTTP 基本一一对应：`codemap:get_file`、`impact`、`check_boundary`、`module_map`、`search`、`stats`、`rebuild`、`acquire_lock`、`check_lock`、`release_lock`、`list_locks`、`report_inaccuracy`、`list_feedback`。能力参数以 `manifest.json` 的 `public_actions` 和运行时 `register_capability` 为准，两者必须保持同名同义；`acquire_lock.ttl` 可省略，默认 600 秒。

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
| 文件锁 | `modules/codemap/data/locks.json` + `locks.json.lock`，temp+rename 原子写，OS 文件锁保护读改写 |
| 表 | `codemap_feedback`、`codemap_metrics` |
| 依赖 | `tree-sitter`、`watchdog` |
| 热更新 | 后端启动后后台建索引，watchdog 500ms 防抖增量更新 |
| 可信度 | `confidence` 是解析覆盖率，`empirical_accuracy` 是基于反馈闭环的实战命中率；当 `codemap_feedback=0` 时返回 `empirical_accuracy:null`、`empirical_accuracy_status:"no_feedback"`，表示暂无反馈样本，不能解读为 100% 准确 |

## 多 Worker 口径

- 代码图索引是 worker 进程内内存状态，`stats.index_scope` 固定为 `process-local`。
- 后端多 worker 启动时每个 worker 都会各自构建索引；`rebuild` 刷新当前处理请求的 worker，并在响应中标明 `rebuild_scope: current_worker`。
- 跨 worker 必须共享的状态已经持久化：`codemap_metrics.query_count`、`codemap_feedback` 在数据库，文件锁在 `modules/codemap/data/locks.json`。
- 验收时不要把单次 `rebuild` 理解为全 worker 广播；需要全 worker 同步刷新时重启后端，或连续请求直到各 worker 均完成本地热更新。

## 边界

- 不索引第三方库、构建产物、sandbox、tests、venv、node_modules。
- 查询返回 `stale` 或 `reliability_note` 时，必须实读文件确认。
- 发现不准后调用 `report_inaccuracy`，不要只在对话里抱怨。

## 验证

模块级回归：

```bash
cd backend && .venv/bin/python -m pytest ../modules/codemap/tests/ -v
cd backend && .venv/bin/python -m pytest ../modules/codemap/sandbox/test_module.py -v
cd backend && .venv/bin/ruff check ../modules/codemap/backend ../modules/codemap/tests ../modules/codemap/sandbox
```

主框架活栈验收（常驻后端 33000/实际端口来自 `backend/logs/.backend.port`）：

```bash
# 读接口必须返回 success:true，且 data 内含 confidence/stale/reliability 相关字段
codemap:stats
codemap:get_file {"path":"modules/codemap/backend/router.py"}
codemap:impact {"path":"modules/codemap/backend/router.py"}
codemap:check_boundary {"module_key":"codemap"}
codemap:module_map {"module_key":"codemap"}
codemap:search {"keyword":"CodemapFeedback"}

# 假成功守卫：不存在文件、空边界参数、空搜索词必须 success:false
codemap:impact {"path":"no/such/file.py"}
codemap:check_boundary {}
codemap:search {"keyword":""}

# 锁持久化守卫：acquire 后 list/check 可见，release 后消失；测试锁必须清理
codemap:acquire_lock {"path":"modules/codemap/README.md","agent_id":"codemap-readme-test","ttl":60}
codemap:check_lock {"path":"modules/codemap/README.md"}
codemap:list_locks {}
codemap:release_lock {"path":"modules/codemap/README.md"}

# 反馈链路守卫：无反馈时 stats 的 empirical_accuracy 必须为 null 且 list_feedback 含 empty_note；
# report 后 list_feedback 可见；验收创建的反馈必须从 codemap_feedback 清理
codemap:stats
codemap:list_feedback {}
codemap:report_inaccuracy {
  "path":"modules/codemap/README.md",
  "query_type":"verification",
  "codemap_said":"temporary verification row",
  "actual":"temporary verification row",
  "reason":"temporary verification row"
}
codemap:list_feedback {"path":"modules/codemap/README.md"}
```
