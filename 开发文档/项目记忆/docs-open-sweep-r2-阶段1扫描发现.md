---
name: "docs-open sweep r2 阶段1扫描发现"
type: "task"
tags: [docs-open, module-sweep, r2, findings, security, false-success, task_id:docs-open-sweep-20260703-r2]
agent: "codex-docs-open-sweep-20260703-r2"
created: "2026-07-03T07:26:11.128570+00:00"
---

阶段1发现：1) docs-open 的 get_authenticated_user 会优先接受 X-Client-Id/X-Open-Id/X-Access-Token 三件套，导致 /api/docs/token、/api/docs/open、/api/docs、/export、/revoke-tokens 等完整用户操作也可被文档 scoped token 认证，再通过框架 file access 以 token subject 的全用户身份访问/签发其他文档 token，存在越权放大风险。2) Token scope、client_id、expiry_hours、mode、doc_type 缺少硬边界，int(fid) 等非法输入可能 500 或签发过长 token。3) handlers/content.py 对 parser 失败返回 {format:'error'}，外层 ApiResponse 仍 success:true，是假成功；xlsx/docx write 调 office-gen 后没有替换原 file，可能假写成功。4) capabilities.py 与 sandbox 契约对真实返回形状不一致，mode/type 未白名单。5) routes 工具拉 openapi 失败，提示当前 33000 后端可能未运行或不可连，后续用 lint/sandbox/可用 probe 验证。
