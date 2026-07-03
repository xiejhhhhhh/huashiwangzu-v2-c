---
name: "IM 模块扫雷修复与验证完成"
type: "task"
tags: [im, sweep, verification, task_id:codex-im-sweep-20260703-r2]
agent: "codex-im-sweep-20260703-r2"
created: "2026-07-03T07:33:04.147074+00:00"
---

完成 IM 模块扫雷。改动范围：modules/im/README.md、backend/init_db.py、backend/models.py、backend/router.py、frontend/index.vue、manifest.json、sandbox/test_module.py。修复：消息内容 trim/非空/4000 字限制；conversation_id/target_user_id/last_read_message_id 参数约束；消息分页 page_size<=100；发送后推进发送者 read_state；未读数排除当前用户自己发送的消息；mark_read 验证 message_id 属于当前会话；capability 参数错误改抛框架结构化异常，不再返回内嵌 success:false 假绿；保留成功路径 success:true 兼容旧调用；新增 POST /api/im/conversations 供前端只建会话不发空消息；manifest notify 补 title 参数；sandbox 改为导入真实 router 的实现级测试。验证：ruff modules/im 后端与 sandbox 全通过；cd backend && PYTHONPATH="$PWD:../modules" .venv/bin/python -m pytest ../modules/im/sandbox/test_module.py -> 7 passed；run_test backend/tests/test_im_capability_permissions.py -> 1 passed；cd frontend && npm run build 通过，扫描生成的 frontend/src 变动已恢复；cd frontend && npx vue-tsc -b 通过；活栈 health/read 接口正常，POST /api/im/conversations 返回 405，说明常驻后端尚未重启加载新 router。测试数据：backend IM 回归测试创建的 marker 数据已由测试 cleanup 清理；本次活栈 probe 未创建业务数据。残留：/api/im/users 仍直接读框架用户表，因为当前 viewer 级公开用户目录接口不存在，应另起框架任务补公共联系人能力后替换。
