---
name: "backend foundation degraded ContentPackage 与私有模块 capability 回滚收口"
type: "task"
tags: [backend, foundation, content-package, private-modules, capability-leak, degraded]
agent: "codex-backend-worker"
created: "2026-07-03T05:39:10.384192+00:00"
---

本轮在 backend foundation 收口中复核并窄补：ContentPackage 增加 consumable 状态口径，parsed/degraded/partial 可被正文读取和下载编译消费；资源诊断 failed/degraded/partial/done_with_errors 只把包状态降级为 degraded，原始 resource_diagnostics/parse_status 保留在 content IR，避免假装资源全成功。private_module_service 通过 import 前 capability 快照与失败回滚 _unregister_new_capabilities 清理 import 期间新增能力，并在正常 deactivate 时清理 tracked capability keys，覆盖激活失败窗口。验证：backend/.venv/bin/ruff check 指定 6 文件通过；cd backend && pytest 指向系统 Python 因缺 sqlalchemy 收集失败；cd backend && .venv/bin/pytest tests/test_private_modules_lifecycle.py tests/test_content_ir_architecture.py tests/test_parser_resource_diagnostics.py -q 结果 71 passed, 1 warning。工作区有大量既有 out-of-scope 改动未回退。commit：未提交。
