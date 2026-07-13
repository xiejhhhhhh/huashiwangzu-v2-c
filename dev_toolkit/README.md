# Project Toolkit MCP

项目工具台是 Agent 开发本项目时的标准 MCP。入口在仓库根目录 `.mcp.json`：

```text
python3.14 dev_toolkit/server.py
```

MCP server id 固定为 `project_toolkit`，以便 Codex 稳定暴露 `mcp__project_toolkit.*`
可点工具名；中文“项目工具台”仅作为文档显示名。

`server.py` 只负责启动、注册和路由；具体工具放在 `dev_toolkit/*_tools.py`。

## 常用流程

```text
brief -> plan_task -> worktree_guard -> 查证据 -> edit -> verify -> docs_audit -> finish_task
```

| 场景 | 工具 |
|---|---|
| 项目概览 | `brief`, `plan_task`, `worktree_guard` |
| 找代码 | `code_explore`, `code_node`, `code_impact` |
| 查契约 | `routes`, `capabilities`, `db_schema`, `capability_contract_diff` |
| 改代码 | `quick_fix_preview`, `quick_fix_patch`, `batch_quick_fix_apply` |
| 查 bug | `bug_logs`, `bug_log_files`, `tail_log` |
| 验证 | `lint`, `run_test`, `probe`, `call_capability` |
| 重启 | `restart_backend` |
| 文档同步 | `docs_audit`, `docs_sync` |
| 发布检查 | `release_gate`, `smoke_all`, `module_sandbox_matrix` |
| Git | `git_sync_plan`, `git_sync_workflow` |

## 日志排障

- `bug_logs`：先用它。汇总最近错误、异常、Traceback、前端网络异常、任务失败。
- `bug_log_files`：列出日志文件、来源、大小、更新时间。
- `tail_log`：只看某个模块原始尾部。
- `clear_log`：会清空日志，只在明确需要时使用。

示例：

```text
bug_logs(query="/api/desktop/state", severity="error", sources="all", limit=20)
bug_logs(module="knowledge", severity="warning", lines=1000)
bug_log_files(sources="modules")
tail_log(module="knowledge", lines=80)
```

## 重启和验证

- 改后端、路由、能力注册、工具台后，先用 `restart_backend()`。
- 重启后用 `probe(method="GET", path="/api/health")` 或目标接口验证。
- `probe` / `call_capability` 返回 `_toolkit_auth`，可直接确认调用使用的 `user_id` 和角色。
- `finish_task` 的 `lint_paths` 支持空格、逗号、换行和 JSON list；`test_env_json` 可传 pytest 环境变量，默认补 `JWT_SECRET=test-secret`。
- 前端改动优先跑对应 build/UI 检查；后端改动优先跑聚焦 pytest。

## 知识库巡检

- `knowledge_pipeline_snapshot` 查看队列、向量回填总量/已完成/运行任务/剩余量、近期速度和预计耗时、DB 压力、最近失败、模型日志和最近 stage 指标。
- `recent_stage_metrics.key_metrics` 会汇总 `vector_candidates`、`db_commit_ms`、`llm_ms` 等关键字段。
- `app.task_worker_main` 是可丢弃的后台队列 worker，不是持久状态。队列行持久化在数据库里；改了 task handler、能力注册或遇到内存退休时，可以直接杀旧 worker。worker 退出恢复会把 running 行释放回可重试状态，`backend_watchdog` 会在有可执行 pending 任务时自动拉起新 worker。

## Agent 巡检

- `agent_runtime_snapshot` 只读分析 Agent 对话轨迹、工具调用和失败签名，输出工具发现开销、文件/参数契约错误、知识库超时、权限前置缺失等问题及对应代码落点。传 `owner_id` 可只看一个用户的对话与轨迹。

## 文档守卫

- 改 manifest、能力注册、router、model、sandbox、release gate、工具台后跑 `docs_audit`。
- 只有生成区块或生成事实漂移时用 `docs_sync`。
- 规则和契约文字手动写到所属 README 或 `开发文档/agent_handoff/`。
- 不把运行记忆、反馈记录、临时审计流水账搬进长期文档。

## 组件规则

新增工具放在独立组件：

```text
dev_toolkit/{domain}_tools.py
  tool_definitions()
  handles_tool(name)
  handle_tool(...)
```

不要把大段工具 schema 或业务逻辑直接写进 `server.py`。

## 高风险工具

- `workspace_reset` 删除工作区数据。
- `clear_log` 截断日志。
- `docs_sync` 写 Markdown。
- `git_sync_workflow` 会 stage、commit、push、合并目标分支；不会 force push、rebase、reset。
- `probe`、`call_capability` 会打当前 live backend。

## 本地验证

```bash
python3.14 -m pytest dev_toolkit/test_log_tools.py dev_toolkit/test_insight_tools.py dev_toolkit/test_server_helpers.py -q
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```
