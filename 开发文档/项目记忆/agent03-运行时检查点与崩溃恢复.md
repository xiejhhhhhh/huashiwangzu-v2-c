## Agent 运行时检查点与崩溃恢复（2026-06-25）

- Agent: platform-robustness-03
- 做了什么：给 Agent 运行时加检查点能力——工具循环每轮后可选保存 messages/tool_events/timeline，worker 崩溃后可用 resume_checkpoint_id 从断点继续。
- 改了哪些：checkpointer.py(新增)、models.py、runtime_policy.py、tool_loop_runtime.py、conversation_runtime.py、schemas.py、chat.py、init_db.py、test_checkpointer.py
- 踩过的坑：SQLAlchemy `text()` 会误解析 JSON 中的 `:number` 为绑定参数 → 改用 `exec_driver_sql` + `$N` 位置参数；`asyncpg` 需要原生 Python `datetime` 而非 ISO 字符串。
- 遗留问题：模型网关 httpx.Timeout 预存 bug 阻塞了 E2E 中断→恢复的在线验证，单元测试覆盖了 saver 全部路径。
