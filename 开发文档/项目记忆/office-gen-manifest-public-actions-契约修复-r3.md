---
name: "office-gen manifest public_actions 契约修复 r3"
type: "task"
tags: [office-gen, manifest, public_actions, contract, frontend-runtime, r3]
agent: "codex-office-gen-manifest-contract-r3"
created: "2026-07-03T10:48:59.819133+00:00"
---

Agent codex-office-gen-manifest-contract-r3 在分支 codex/sweep-quality-r2 修复 office-gen manifest public_actions 参数元数据漂移；未 commit/push。改动仅在 modules/office-gen/manifest.json：docx/xlsx/pptx/pdf 补齐 content_ir 与 folder_id；generate_to_artifact 拆除 content/sheets/slides、blocks/content_ir 伪字段，改为 content/sheets/slides/blocks/content_ir/folder_id；replace_existing 补 filename 并拆除伪字段。验证：python3.14 -m json.tool 通过；jq 参数键清单无斜杠伪字段；capabilities(module=office-gen) 返回新清单；backend/.venv pytest modules/office-gen/sandbox/test_module.py 8 passed；modules/office-gen/tests/test_generator.py 22 passed；cd backend && .venv/bin/python -m ruff check ../modules/office-gen/backend ../modules/office-gen/tests ../modules/office-gen/sandbox 通过；probe GET /api/office-gen/health 返回 success true。当前 worktree 另有并行 dirty：dev_toolkit/smoke.py、modules/excel-engine/manifest.json，非本 agent 改动。commit: none.
