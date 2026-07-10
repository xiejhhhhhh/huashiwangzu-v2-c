# Project Toolkit MCP

项目工具台是 Agent 开发本项目时的标准 MCP。入口在仓库根目录 `.mcp.json`：

```text
python3.14 dev_toolkit/server.py
```

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
- 前端改动优先跑对应 build/UI 检查；后端改动优先跑聚焦 pytest。

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
