---
name: "post-convergence reset_runtime_data 安全补漏"
type: "task"
tags: [reset-runtime, maintenance, backend, safety, post-convergence]
agent: "codex-post-convergence-reset-worker"
created: "2026-07-03T17:55:43.431812+00:00"
---

# 改了什么

- `backend/scripts/maintenance/reset_runtime_data.py` 改为先查询 public FK 图并计算依赖闭包；apply 时如闭包触达当前 scope allowlist 外的表会拒绝并输出 offending tables；执行 SQL 改为 `TRUNCATE ... RESTART IDENTITY RESTRICT`，不再无审计使用 CASCADE。
- 保留 `--allow-non-local-db` 但加双保险：非本地 DB 必须同时满足 `RESET_RUNTIME_ALLOW_REMOTE_DEV=1` 且 `APP_ENV` 为 `development` 或 `test`。
- `--clean-files` 改为 scope-specific：files 只清 uploads/workspaces/.tmp_downloads/.tmp_exports，agent 只清 backend/data/agent，all-runtime 合并两者。
- 增加 `BACKEND_DATA_DIR` 自身安全校验：拒绝 symlink，resolve 后必须在 backend root 下，且不得是 `/`、home、repo root 或 backend root。
- apply CLI 必须显式传 `--scope`；dry-run 仍默认 `all-runtime`。
- DB backup 目录 manifest 校验 `database_name`/等价字段与当前 DB 一致；普通备份文件要求非空并保留在输出。
- `backend/tests/test_reset_runtime_data.py` 扩充到 19 个测试，覆盖 FK 越界拒绝、合法闭包执行、远程库开关、scope runtime dirs、BACKEND_DATA_DIR、备份和 CLI scope。

# 验证了什么

- `cd backend && pytest tests/test_reset_runtime_data.py`：19 passed。
- `backend/.venv/bin/python -m ruff check backend/scripts/maintenance/reset_runtime_data.py backend/tests/test_reset_runtime_data.py`：All checks passed。
- `probe GET /api/health`：200，`success: true`，status ok。
- `finish_task` 边界检查通过；并行 worker 的 `dev_toolkit/**` 与 `frontend/tests/ui-e2e.spec.mjs` 已作为外部已知变更，不属于本 agent 改动。

# 是否还有残留风险

- 未做真实数据库 destructive apply；本任务用 fake asyncpg 覆盖安全分支，避免触碰活库数据。
- 关联 commit：未提交。
