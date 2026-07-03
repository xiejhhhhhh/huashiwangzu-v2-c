---
name: "主会话验收 im r2 消息契约修复"
type: "task"
tags: [verification, im, r2]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:40:43.279003+00:00"
---

主会话完成 IM r2 修复验收。验证结果：ruff 覆盖 modules/im/backend 与 sandbox/test_module.py 通过；pytest modules/im/sandbox/test_module.py 7 passed；backend tests/test_im_capability_permissions.py 1 passed；routes(filter=/api/im) 显示 GET/POST /api/im/conversations、新 messages/read/users/unread-count 等路由；capabilities(module=im) 显示 notify/send 且 notify 含 title 参数；GET /api/im/conversations 200 空列表；GET /api/im/unread-count 200 unread_count=0；POST /api/im/conversations target_user_id=0 返回统一 422；POST /api/im/messages conversation_id=0/content='' 返回统一 422；im:send 空内容返回 422；im:notify 空内容返回 422。未创建业务测试数据。残留：/api/im/users 仍直接读框架用户表，需后续框架任务提供 viewer 级联系人公共能力后迁出。
