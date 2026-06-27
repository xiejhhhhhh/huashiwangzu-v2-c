---
name: "Agent thinking implicit feedback loop"
type: task
tags: ["agent", "thinking-router", "implicit-feedback", "signals"]
created: 2026-06-27
agent: zcode
---

完成 Agent 思考等级隐式反馈闭环：新增 `agent_thinking_level_signals` 表，用于记录系统从用户后续输入里推断出的自动反馈信号；`run_init()` 会幂等创建该表和索引。`conversation_runtime.py` 在普通对话和编辑重跑装配上下文前调用 `record_implicit_thinking_signal()`，当用户输入命中“太简单/不够/深入/详细/不对/太复杂/简短点”等模式时，会回看同会话上一条 `agent_thinking_levels` 记录，写入一条原等级负向信号和一条期望等级正向信号。`thinking_router.py` 在规则层之后、旧经验库之前读取 `agent_thinking_level_signals`，按文本相似度、时间衰减和 score_delta 聚合，得分为正且超过阈值时以 `source=signals` 返回建议等级；规则层仍然最高优先级。验证：`thinking_router.py`、`conversation_runtime.py`、`init_db.py` ruff 全绿；`run_test backend/tests/test_agent_regression.py` 75 passed；重启后 SQL 验证新表存在；真实对话中先问“解释一下这个功能”，再发“太简单了，详细分析一下”，自动写入 `implicit_correction` medium -0.6 和 `implicit_expected_level` high +0.8 两条信号。
