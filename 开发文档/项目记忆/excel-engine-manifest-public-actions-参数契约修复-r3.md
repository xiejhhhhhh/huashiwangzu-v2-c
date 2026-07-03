---
name: "excel-engine manifest public_actions 参数契约修复 r3"
type: "task"
tags: [excel-engine, manifest, public_actions, capability-contract, r3]
agent: "codex-excel-engine-manifest-contract-r3"
created: "2026-07-03T10:50:39.251056+00:00"
---

修复 frontend/runtime 只读审计发现的 excel-engine manifest public_actions 参数元数据漂移。改动限定 modules/excel-engine：manifest.json 将 create_workbook/import_file_to_workbook/update_range/append_rows/undo/redo/list_history/list_versions/restore_version/export_xlsx/compile_xlsx/publish_to_desktop 的 parameters 同步为后端 register_capability 的 JSON Schema 元数据，补齐 state_key、sheet、start_row、start_col、folder_id、target_file_id、required 等发现字段；parse 与注册表一致保持不变。sandbox/test_module.py 新增 test_manifest_public_actions_match_registered_parameters，导入后端 router 注册能力后对比 manifest 与 list_capabilities 的 action/min_role/parameters，防止后续漂移。验证：ruff check modules/excel-engine/sandbox/test_module.py 通过；官方 sandbox 命令 cd modules/excel-engine/sandbox && PYTHONPATH=../../../backend:.. ../../../backend/.venv/bin/python test_module.py 通过；工具台 run_test modules/excel-engine/sandbox/test_module.py 为 13 passed；python3.14 scripts/check-capability-drift.py OK；/api/excel-engine/health 和 /api/health 200。未 commit/push。注意：收工时全局 worktree 有其他 agent 的 dev_toolkit/smoke.py、modules/office-gen/manifest.json 与 office-gen 项目记忆 dirty，本任务未触碰。
