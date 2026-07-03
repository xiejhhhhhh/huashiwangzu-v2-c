---
name: "office-gen sweep r2 空输出与 Content IR 兼容修复完成"
type: "task"
tags: [office-gen, module-sweep, content-ir, artifact, validation, task_id:office-gen-sweep-20260703-r2]
agent: "codex-office-gen-sweep-20260703-r2"
created: "2026-07-03T07:05:11.733133+00:00"
---

# 改了什么

codex-office-gen-sweep-20260703-r2 仅修改 modules/office-gen/**（另写项目记忆/反馈）。修复点：

1. `backend/generator.py`：docx/xlsx/pptx/pdf 低层生成器拒绝空 content/sheets/slides，以及不可渲染块，避免合法空文件/假成功；补齐 Content IR `blocks`、`content_ir.blocks`、`data.text/title/name`、`data.headers/data.columns/data.rows`、spreadsheet `sheet.children[].table/range`、presentation `slide.children` 兼容。
2. `backend/router.py`：能力入口接受 `blocks/content_ir` 别名；入参和生成校验错误转框架 `ValidationError`，不再以内层 ValueError 变成 500；artifact/replace 生成链路复用相同校验。
3. `backend/converter.py`：LibreOffice 转换完成后检查输出 bytes 非空，0 字节输出直接失败，不登记空产物。
4. `manifest.json` / `README.md`：同步公开能力参数说明，声明 Content IR 别名和空输出拒绝策略。
5. `tests/test_generator.py` / `sandbox/test_module.py`：新增空输出拒绝、Content IR sheet/slide/table 嵌套兼容测试。

# 验证了什么

- `cd backend && .venv/bin/python -m ruff check ../modules/office-gen/backend ../modules/office-gen/tests ../modules/office-gen/sandbox`：All checks passed。
- `run_test ../modules/office-gen/tests/test_generator.py`：22 passed。
- `backend/.venv/bin/python modules/office-gen/sandbox/test_module.py`：5 PASS。
- `probe GET /api/office-gen/health role=editor`：200，success true，libreoffice true。
- `call_capability office-gen:docx` 空 content：success false，无文件产物创建。主后端进程未强制重启，以免打断并行 worker；新 router ValidationError 行为由代码/单测覆盖，下一次后端重启后生效。

# 边界

本 worker 自己的代码改动仅在 `modules/office-gen/**`；项目记忆/反馈在 `开发文档/项目记忆/**`。工作区仍有 codemap/image-gen/knowledge/terminal-tools/data uploads 等并行 worker 改动，未触碰未回滚。

# 关联 commit

暂无；主会话统一提交。
