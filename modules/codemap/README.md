# codemap — 代码地图服务

常驻内存代码索引服务，为 Agent 提供一次 API 调用的影响面分析和边界合规检查。

## 概述

- **目标**：把 Agent "N 次工具逐层翻文件" 换成 "1 次查表"，不烧 LLM token
- **索引模型**：文件节点 + 符号节点 + 5 种边 (import / call / capability_register / capability_call / db_table)
- **扫描范围**：`backend/app/*`、`frontend/src/*`、`modules/*`
- **扫描排除**：自动跳过 `node_modules`、`.venv`、`dist`、`__pycache__`、`.git`、`data`、`sandbox`、`tests` 等第三方/构建/测试目录。**不索引第三方库**。
- **语言支持**：Python (ast)、TypeScript/Vue (regex)
- **热更新**：watchdog 监听文件变更，500ms 防抖增量更新
- **可信度**：stats 返回 0-100 confidence（基于就绪 + 解析成功率 + 新鲜度）；`get_file`/`impact` 返回 `stale` 标记

## 模块结构

```
modules/codemap/
  manifest.json          # 模块身份，background-service
  requirements.txt       # tree-sitter>=0.25, watchdog>=6.0
  backend/
    router.py            # HTTP 端点 (11) + 跨模块能力注册 (11)
    graph.py             # 内存图数据结构 + 查询算法
    indexer.py           # 文件扫描 + 多语言解析
    boundary_engine.py   # 边界规则引擎
    watcher.py           # watchdog 热更新
    file_lock.py         # 跨 worker 文件持久化锁
  data/                  # 持久化数据目录（已 .gitignore）
  tests/
    test_codemap.py      # 24 个单元测试
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/codemap/health` | 健康检查 |
| GET | `/api/codemap/stats` | 索引统计（含 confidence/解析失败/新鲜度/实战信任分） |
| POST | `/api/codemap/get-file` | 文件级代码地图（含 stale 标记 + reliability_note） |
| POST | `/api/codemap/impact` | 影响面分析（传递闭包，含 stale 标记 + reliability_note） |
| POST | `/api/codemap/check-boundary` | 边界合规检查 |
| POST | `/api/codemap/module-map` | 模块总览 |
| POST | `/api/codemap/search` | 关键词搜索 |
| POST | `/api/codemap/rebuild` | 全量重建索引（admin） |
| POST | `/api/codemap/acquire-lock` | 获取文件锁（跨 worker） |
| POST | `/api/codemap/check-lock` | 检查文件锁 |
| POST | `/api/codemap/release-lock` | 释放文件锁 |
| GET | `/api/codemap/list-locks` | 列出所有活跃锁 |
| **POST** | **`/api/codemap/report-inaccuracy`** | **反馈 codemap 查询不准（Agent 实读验证后调用）** |
| **GET** | **`/api/codemap/list-feedback`** | **查看反馈记录（仅 admin，按投诉频次排序）** |

## 跨模块能力（供 Agent 技能发现器使用）

| 能力 key | 入参 | 返回 |
|----------|------|------|
| `codemap:get_file` | `{path}` | 文件节点、依赖、被依赖、能力、表、stale、**reliability_note** |
| `codemap:impact` | `{path, symbol?}` | 正向+反向传递闭包、风险等级、stale、**reliability_note** |
| `codemap:check_boundary` | `{path? , module_key?}` | 违规清单或"合规" |
| `codemap:module_map` | `{module_key}` | 暴露/消费的能力、边界健康 |
| `codemap:search` | `{keyword}` | 匹配的文件和符号 |
| `codemap:stats` | `{}` | 索引规模、耗时、就绪状态、confidence、**empirical_accuracy/feedback_count/recent_complaints** |
| `codemap:rebuild` | `{}` | 全量重建索引（admin） |
| `codemap:acquire_lock` | `{path, agent_id, ttl?}` | 获取文件锁 |
| `codemap:check_lock` | `{path}` | 检查文件锁 |
| `codemap:release_lock` | `{path}` | 释放文件锁 |
| `codemap:list_locks` | `{}` | 列出所有活跃锁 |
| **`codemap:report_inaccuracy`** | `{path, query_type, codemap_said, actual, reason}` | **记录反馈（Agent 发现不准时调用）** |
| **`codemap:list_feedback`** | `{path?, page?, page_size?}` | **查看反馈（仅 admin，按投诉频次排序）** |

## 查询示例

```bash
# 文件信息
curl -X POST http://127.0.0.1:33000/api/codemap/get-file \
  -H "Content-Type: application/json" \
  -d '{"path": "modules/agent/backend/router.py"}'

# 影响面分析
curl -X POST http://127.0.0.1:33000/api/codemap/impact \
  -H "Content-Type: application/json" \
  -d '{"path": "backend/app/database.py"}'

# 边界检查
curl -X POST http://127.0.0.1:33000/api/codemap/check-boundary \
  -H "Content-Type: application/json" \
  -d '{"module_key": "agent"}'
```

### 维修 codemap 前先查反馈

不要空想哪里不准。先查 `GET /api/codemap/list-feedback`（仅 admin），按投诉频次排序，定位高频投诉的路径和解析缺陷，然后针对性修。

反馈落库在 PostgreSQL `codemap_feedback` 表（`codemap_` 前缀，跨 worker 一致），每个反馈记录文件路径、查询类型、codemap 说的、实际情况、原因。Agent 实读验证后调 `POST /api/codemap/report-inaccuracy` 记录。

## 经验信任分

stats 返回两个分：
- `confidence`：静态解析覆盖率（基于就绪+解析成功率+新鲜度）
- `empirical_accuracy`：实战命中率（基于 `1 - 投诉/窗口内查询次数`），0-100。区分自评分和实战分。

`get_file` 和 `impact` 返回 `reliability_note`：若该文件解析失败/索引过期/被投诉过，附加人话说明原因。没有问题不加 note。

并行任务（多 Agent 改文件）应遵循：
1. 改文件前先 `check_lock` 检查目标文件是否被锁
2. 有活锁 → 跳过或等待
3. 无锁 → `acquire_lock` → 改文件 → `release_lock`
4. TTL 到期自动释放，防 Agent 崩溃后锁残留

## 依赖

- `tree-sitter>=0.25.0` — Python 绑定，保留（未来可扩展 TS 语法树解析）
- `watchdog>=6.0.0` — 文件系统监听

安装方式（已纳入共享 `.venv`）：

```bash
cd backend && source .venv/bin/activate
pip install tree-sitter watchdog
```

## 运行测试

```bash
cd backend && .venv/bin/python -m pytest ../modules/codemap/tests/ -v
```

## 索引模型

### 节点

- **FileNode**: `path`, `layer` (framework-backend / framework-frontend / module), `module_key`, `language`, `symbols`
- **SymbolNode**: `id` (`{path}::{name}`), `name`, `kind` (function / class), `file`, `start_line`, `end_line`

### 边

| 边类型 | 方向 | 元数据 |
|--------|------|--------|
| `import` | file → file | cross_module, line, imported_name |
| `call` | symbol → symbol | source_line |
| `capability_register` | file → "module:action" | kind="register", line |
| `capability_call` | file → "module:action" | kind="call", line |
| `db_table` | file → table_name | line |

### 边界规则

按 AGENTS.md 铁律 17-20 自动标记：
1. 模块文件 import 其他模块内部文件 → 违规
2. 模块文件 import 框架内部文件（非公开 API）→ 违规
3. 模块操作 `framework_*` 表 → 违规
4. 模块操作其他模块的表 → 违规

## 构建与热更新

- 后端启动时**异步后台线程**构建索引，不阻塞启动
- 索引就绪前，查询返回 `{status: "indexing"}`
- watchdog 监听文件变更，**500ms 防抖合并**，只增量重解析受影响文件
- 查询始终读当前快照，更新期间不阻塞
- `POST /api/codemap/rebuild` 可手动触发全量重建（admin）
