---
name: "Agent edit-resubmit 验收与补修"
type: task
tags: ["agent", "验收", "edit-resubmit", "soft-branch", "context", "fix"]
created: 2026-06-27
agent: zcode
---

验收 opencode 交付的 Agent 消息原地编辑与软分支回退重跑，不采信报告，做了代码/DB/活系统复核。确认其主功能基本落地：edit-resubmit 路由存在，agent_messages 增 status/edited_from_message_id/branch_root_message_id，消息列表按 active 过滤，旧尾部消息 archive。核验发现并就地修复两个关键问题：1) edit-resubmit 删除旧事件后没有重写 B' user_msg，导致下一轮上下文缺编辑后的用户消息；已在 ConversationRuntime.execute_edit_resubmit 装配当前上下文后 record_event('user_msg', {'content': content, 'edited_message_id': message_id})。2) ToolLoopRuntime final persist 因 add_message_meta 不接受 usage 参数失败，导致 assistant meta/events/hooks 不落库；已给 AgentMessageMeta 增 usage JSON、add_message_meta 增 usage 参数、get_messages_with_meta 返回 usage、init_db 增 ensure_message_meta_usage_column。验证：ruff 相关文件通过；tests/test_agent_regression.py 75 passed；重启后 /api/health module_errors=null；活系统会话 41 执行 A/B/C→edit B'，旧 C 为 archived，GET messages 不返回旧 C，agent_events 有 user_msg B' 和 assistant_msg 新回复，日志 persist_assistant/persist_pending_events 成功无 usage 报错。测试会话 39/40/41 已删除。
