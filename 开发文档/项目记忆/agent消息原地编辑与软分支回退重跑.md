---
name: "Agent消息原地编辑与软分支回退重跑"
type: architecture
tags: ["agent", "edit-resubmit", "soft-branch", "message-editing"]
created: 2026-06-27
agent: opencode
---

将 Agent 消息编辑从"rollback+复制到输入框"改为"原地编辑+软分支重跑"。

数据方案：agent_messages 表新增 status(active/archived)、edited_from_message_id、branch_root_message_id 三列（无痛迁移，IF NOT EXISTS）。编辑确认时：更新消息内容 → 后续消息 status=archived → 删旧事件(含编辑点的 user_msg 事件) → 删旧 checkpoint → context assembly 只投影编辑前历史 + 编辑后内容作为 current_input → SSE 流式回复。

新接口：POST /api/agent/conversations/{id}/messages/{msg_id}/edit-resubmit，body: {content, profile_key}，返回 SSE 流。

前端：提取共享 SSE 处理器 processStreamResponse，sendMessage 和 handleSubmitEdit 共用。handleSubmitEdit 不再调用 rollback 端点，不再填充底部输入框。

关键约束：只能编辑 role=user 的消息；空 content 拒绝；验证 owner+conversation 归属；所有消息查询(status=active)过滤。
