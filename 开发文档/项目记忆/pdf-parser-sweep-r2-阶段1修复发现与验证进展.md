---
name: "pdf-parser sweep r2：阶段1修复发现与验证进展"
type: "task"
tags: [pdf-parser, module-sweep, r2, validation, false-success, sandbox, task_id:pdf-parser-sweep-20260703-r2]
agent: "codex-pdf-parser-sweep-20260703-r2"
created: "2026-07-03T07:42:31.509175+00:00"
---

阶段1完成主要修复：

1. `modules/pdf-parser/backend/router.py`
- 确认主链路已通过框架 `run_uploaded_file_capability`，因此 file_id 会经 `read_uploaded_file`/`check_file_access` 做 owner/share 校验后才读盘。
- 新增模块内 `_require_positive_file_id`，把负数、非数字、缺失 file_id 转成框架 `ValidationError`，避免共享 runner 的裸 `ValueError` 变成 500。
- 新增 `_ensure_non_empty_parse_result`，当 PDF 解析结果同时无 blocks、无 resources 时拒绝成功，避免“空解析假成功”。
- `page.extract_tables()` 改为 `page.extract_tables() or []`，防空页/异常 extractor 返回 None 时迭代崩。

2. `modules/pdf-parser/sandbox/test_module.py`
- sandbox 从只验骨架升级为真实样例验收：必须用 sample.pdf 解析出非空 blocks/resources，且至少有非空文本 block；页码必须为 >=1。
- 输出 contract 对齐后端英文类型：heading/paragraph/table/image；resource 字段对齐 mime_type/filename/description/page。
- 增加 pytest 负例：空 blocks/resources 不允许通过 sandbox validation。

3. `modules/pdf-parser/README.md`
- 补充可复现 sandbox 命令，明确使用 `backend/.venv/bin/python`，避免裸 python 缺 pdfplumber。

验证已完成：ruff 两个 Python 文件通过；`backend/.venv/bin/python modules/pdf-parser/sandbox/test_module.py` 通过；工具台 `run_test modules/pdf-parser/sandbox/test_module.py` 2 passed；`modules/pdf-parser/sandbox npm run build` 通过；活栈现有 PDF `file_id=2013` 经 `pdf-parser:parse` 和 `/api/pdf-parser/parse` 均 success true，返回 1 个 heading block。注意：活栈负数 file_id 探针仍返回旧 500，判断常驻后端未重载本次模块代码；未按任务要求重启服务，需主会话重启后新防线在线生效。
