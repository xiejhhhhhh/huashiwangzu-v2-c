---
name: "docs-open sweep r2 修复与验证完成"
type: "task"
tags: [docs-open, module-sweep, r2, security, false-success, verification, task_id:docs-open-sweep-20260703-r2]
agent: "codex-docs-open-sweep-20260703-r2"
created: "2026-07-03T07:33:24.715783+00:00"
---

本轮完成 modules/docs-open 扫雷和修复：1) 新增 validators.py，统一校验 client_id、scope.doc_ids/edit_doc_ids、expiry_hours、mode、doc_type、title，token scope 必须非空且 doc id 为正整数，expiry <= 24h。2) 收紧鉴权边界：require_docs_permission 默认只接受框架 JWT bearer；只有 GET/POST /api/docs/{file_id}/content 允许 scoped docs-open token，且随后经 check_doc_access + 框架 check_file_access/check_file_write_access；raw file 的非 query-token fallback 改为 JWT only，避免 scoped token 伪装成完整用户。3) token hash 从 uuid5 迁到 sha256，保留 legacy hash 校验以兼容短期旧 token。4) content 读取 parser 失败改为抛 AppException，不再 success:true 包 error；xlsx/docx 写回因未真实替换原文件，改为 400 unsupported，避免假成功。5) capabilities.py 参数边界与返回形状补齐 file_id；manifest public_actions 增加 enum；README 写清 scoped token 非完整登录态、可复现 sandbox 命令。6) sandbox/test_module.py 从静态假形状改为真实 helper 契约测试，覆盖 token/scope/expiry/client_id/mode/type/hash/auth-boundary。

验证：mcp lint 对 router/models/token_service/auth/content/capabilities/validators/sandbox 全部通过；`PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py` 通过；工具台 run_test pytest sandbox 6 passed；`PYTHONPATH=backend backend/.venv/bin/python -m compileall -q modules/docs-open/backend modules/docs-open/sandbox/test_module.py` 通过；/api/health probe 200 success:true。活系统对 docs-open:open 非法参数仍返回 500，判断需要主会话重启后端加载本轮代码后再复验（也可能暴露 registry 对 capability AppException 的映射需另做框架任务，当前任务不能改 backend/app）。未创建测试数据，未清理 data/uploads，未触碰 backend/app、frontend/src、其他模块。worktree_guard 全仓失败来自并发 worker 的既有/新增改动，本任务 docs-open 改动在边界内。
