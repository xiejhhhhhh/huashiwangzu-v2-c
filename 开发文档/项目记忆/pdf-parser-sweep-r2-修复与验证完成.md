---
name: "pdf-parser sweep r2：修复与验证完成"
type: "task"
tags: [pdf-parser, module-sweep, r2, completed, validation, permissions, false-success, sandbox, task_id:pdf-parser-sweep-20260703-r2]
agent: "codex-pdf-parser-sweep-20260703-r2"
created: "2026-07-03T07:43:19.320297+00:00"
---

本任务完成：对 `modules/pdf-parser` 做模块级扫雷并完成必要修复。

改动文件：
- `modules/pdf-parser/backend/router.py`
- `modules/pdf-parser/sandbox/test_module.py`
- `modules/pdf-parser/README.md`

核心结论与修复：
1. file_id 权限链路：确认 pdf-parser 后端解析主链路调用 `run_uploaded_file_capability`，框架内部会通过 `read_uploaded_file` -> `check_file_access` 校验 owner/share，再解析物理文件；未发现裸 `db.get(File)` 后直接读盘。
2. 统一错误语义：新增 `_require_positive_file_id`，把负数、非数字、缺失 file_id 收敛为 `ValidationError`，避免共享 runner 裸 `ValueError` 导致 500。
3. parser 假成功：新增 `_ensure_non_empty_parse_result`，当 blocks/resources 同时为空时拒绝成功，避免空 PDF/不可抽取 PDF 被当成成功解析进入下游。
4. 空内容/页码边界：`extract_tables()` 改为 `or []`；sandbox 强制真实样例输出至少一个非空文本 block，所有 page 必须是 >=1 的 int。
5. sandbox 真验收：sandbox 输出 contract 对齐后端英文 block/resource 字段，并增加空结果负例；README 写明用 backend venv 跑测试。
6. manifest/backend capability：manifest `public_actions` 与运行时 `register_capability("pdf-parser", "parse", ...)` 均为 viewer + file_id，能力清单和路由一致。

验证：
- `ruff check modules/pdf-parser/backend/router.py modules/pdf-parser/sandbox/test_module.py`：通过。
- `backend/.venv/bin/python modules/pdf-parser/sandbox/test_module.py`：通过，真实 sample.pdf 解析出 1 个 heading block。
- 工具台 `run_test modules/pdf-parser/sandbox/test_module.py`：2 passed。
- `cd modules/pdf-parser/sandbox && npm run build`：通过，仅 Vite/Rollup 常规体积 warning。
- 本地导入新 router helper：负数/非数字/缺失 file_id 均抛 `ValidationError`；空 blocks/resources 抛 `ValidationError`；非空结果通过。
- 活栈 33000：`pdf-parser:parse` 和 `/api/pdf-parser/parse` 对现有 `file_id=2013` 均返回 `success:true`，blocks=[heading hello]。未新增上传/测试数据。

残留风险：
- 常驻 33000 后端未重载本次模块代码，负数 file_id 活栈探针仍显示旧 500；按任务要求未重启常驻服务，需主会话重启后新入口防线在线生效。
- 全仓仍有 docs-open/docx-parser/xlsx-parser/data/uploads 等并发脏文件，已确认不属于本 agent 改动，未触碰、未回退。
