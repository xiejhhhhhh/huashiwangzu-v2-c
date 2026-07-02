---
name: "release-verification-r4发布前验证矩阵结果"
type: "task"
tags: [release-verification-r4, release-gate, verification, 20260703]
agent: "release-verification-r4"
created: "2026-07-02T16:58:49.418949+00:00"
---

# 任务
作为发布前独立验收代理，基于当前工作区运行稳定 checkpoint 前验证矩阵；不改业务代码。

# 验证结果
- `cd backend && .venv/bin/python -m pytest ../modules/knowledge/backend/tests/test_pipeline_stage_semantics.py ../modules/knowledge/backend/tests/test_ingest_status_service.py tests/test_knowledge_pipeline_lifecycle.py tests/test_module_boundary_contracts.py tests/test_module_capability_drift.py tests/test_memory_core_paths.py tests/test_empty_flow_audit_regressions.py -q`：80 passed。
- `python3.14 -m pytest dev_toolkit -q`：92 passed，用时 159.02s。
- `backend/.venv/bin/python -m pytest modules/memory/sandbox/test_module.py -q`：24 passed。
- `backend/.venv/bin/python -m pytest modules/knowledge/tests/test_raw_collection.py modules/knowledge/backend/tests/test_ingest_status_service.py modules/knowledge/backend/tests/test_pipeline_stage_semantics.py -q`：17 passed。
- `cd frontend && npm run build`：通过，Vite 仅有大 chunk warning。
- `git diff --check`：通过。
- `python3.14 dev_toolkit/release_gate.py --skip-ui`：PASS_WITH_DEBT，release_safe=true，无 BLOCKER；health/system/queue delta/sandbox 通过，债务为 UI 跳过、历史队列 failed=902、historical failed debt=500、recent failed=3。

# 重要发现
MCP `release_gate(skip_ui=true)` 工具在同一工作区曾返回 `task queue audit missing summary.failed`，但命令行当前源码的 `dev_toolkit/release_gate.py --skip-ui` 正常解析 `/api/tasks/worker/audit`，接口实际返回 `data.summary.failed=902`。判断为 MCP 进程/包装层与当前源码不同步或入口口径问题，而不是业务接口缺字段。

# 验证噪音
我误用 `python3.14 dev_toolkit/smoke.py --help` 和 `python3.14 dev_toolkit/smoke.py --skip-ui`，该脚本不解析 CLI 参数，导致两次完整 UI smoke 被执行，新增 3 条 recent failed 队列噪音。之后按真实 gate 方式 `SMOKE_SKIP_UI=1 python3.14 dev_toolkit/smoke.py` 与命令行 release gate 均确认 gate-run failed delta 为 0。不建议直接清 failed 行，应交由队列债治理分类处理。

# 代码变更
本 agent 未修改代码文件。
