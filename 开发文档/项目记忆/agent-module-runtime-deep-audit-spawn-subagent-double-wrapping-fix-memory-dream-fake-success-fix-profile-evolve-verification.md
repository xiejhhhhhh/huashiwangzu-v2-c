---
name: "Agent module runtime deep audit: spawn_subagent double-wrapping fix, memory_dream fake success fix, profile_evolve verification"
type: "task"
tags: [agent, runtime, audit, spawn_subagent, fake-success, profile-evolve]
agent: "opencode-r4-agent-runtime"
created: "2026-07-03T05:13:05.037033+00:00"
---

## 改了什么

### P0: `_cap_spawn_subagent` 双重包装修复 — `modules/agent/backend/handlers/tool.py`
- 删除了 `{"success": True, "data": {...}}` 外层包装，直接返回业务数据 `{"results": [...], "total_tasks": ..., "completed": ..., "errors": ...}`
- 原因：capability handler 返回的是业务载荷，框架 call_capability() 透传此结果。返回 `{"success": True, "data": {}}` 会导致双重嵌套，消费者端出现 `resp["data"]["data"]` 这种结构。

### P1: `_handle_memory_dream` 假成功修复 — `modules/agent/backend/handlers/tasks.py`
- 在返回 `{"status": "ok"}` 之前增加了 `result.get("error")` 检查
- 原因：当 memory:dream 返回 `{"error": "..."}` 时（没有 `success` 字段），原代码的 `result.get("success") is False` 会得到 `None != False` 而跳过，最终返回 `{"status": "ok"}` 掩盖失败。

### profile_evolve.py 脏 diff 验证通过
- 已存在的脏 diff（LLM 空响应/不可解析时返回 `{"status": "failed", "error": ..., "retryable": True}` 而非旧 watermark + `{"status": "skipped"}`）符合测试预期。
- `test_agent_profile_evolve_soft_failure.py` (3 tests) 全部通过。

## 验证
- ruff 静态检查 3 文件全部通过
- 28 tests 全部通过: profile_evolve (3), tool_loop_runtime (5), fallback_chain (4), signals (11), subagent_runner (1), action_policy (4)
- git diff --name-only 确认本次增量改动仅为 modules/agent/ 内的 2 文件

## 残留风险
- spawn_subagent 返回值形状变化：之前 `resp["data"]["results"]`, 现 `resp["results"]`。所有模块内消费者已验证通过，但外部直接 call_capability("agent", "spawn_subagent", ...) 的调用者需留意。

## 关联
- 已有 branch: codex/repair-agent-foundation-09-r1
