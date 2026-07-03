---
name: "主会话验收 docs-open r2 token 与假成功修复"
type: "task"
tags: [verification, docs-open, r2, security]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:43:43.593975+00:00"
---

主会话完成 docs-open r2 修复验收。验证结果：ruff 覆盖 modules/docs-open/backend 与 sandbox/test_module.py 通过；pytest modules/docs-open/sandbox/test_module.py 6 passed；compileall 通过；routes(filter=/api/docs) 显示 /api/docs、/api/docs/open、/api/docs/token、/api/docs/{file_id}/content/file/export/revoke-tokens 等真实路由；capabilities(module=docs-open) 显示 open/get_content/create_doc。此前子代理提到非法 docs-open:open 可能 500，主会话重启后复验 docs-open:open file_id=0/mode=admin 返回结构化 400，create_doc 空 title 返回结构化 400。HTTP 活测：/api/docs/token expiry_hours=25 返回 422，bad client_id 返回 400，doc_ids=[0] 返回 400，unsupported scope all 返回 400；/api/docs/open mode=admin 返回 400；/api/docs/0/content 返回 404；/api/docs/0/file 缺 token triple 返回 403。未创建业务测试数据。主会话额外修复 handlers/embed.py 的未用 os/editor 静态问题。
