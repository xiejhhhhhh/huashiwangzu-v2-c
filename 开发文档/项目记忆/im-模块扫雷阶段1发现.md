---
name: "IM 模块扫雷阶段1发现"
type: "task"
tags: [im, sweep, findings, boundary]
agent: "codex-im-sweep-20260703-r2"
created: "2026-07-03T07:24:54.737896+00:00"
---

阶段1证据：IM router 暴露 /conversations、/messages、/read、/unread-count、/users，两项 capability 为 im:notify(editor) 与 im:send(viewer)，DB 只有 im_conversations/im_messages/im_read_state 且都有生产数据。发现：page_size 无上限；send/notify capability 参数错误返回内嵌 success:false，可能被外层包装成 HTTP 200 假成功；send_message 允许空 content，前端 startChat 会尝试发空消息建会话；未读数统计包含自己发的消息；mark_read 不验证 last_read_message_id 属于当前会话；sender 发消息后未自动更新自己的 read_state；/api/im/users 直接读取框架 User 表，当前公开 /api/users/* 对 viewer 403，需后续框架任务提供 viewer 级联系人/用户目录公共能力后再彻底移除该直接读表。
