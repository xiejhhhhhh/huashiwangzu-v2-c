---
name: agent引擎健壮性收口-异常兜底与回归验证
type: audit
tags: [agent, 健壮性, 异常兜底, 回归测试, 多worker, 审计]
created: 2026-06-24
agent: 小马仔(Claude)
commit: 2944ede
---

# Agent 引擎健壮性收口 — 异常兜底与回归验证

## 做了什么

opencode 接单执行，小马仔亲手真打活系统审计。本批次对 Agent 引擎进行健壮性收口：

1. **对话异常兜底** — `chat.py:_yield_final_stream` 全局 try/except，异常降级为 error 事件不崩对话；`parse_inline_tool_calls` 加 try/except，失败降级为无内联调用继续流程
2. **文件读取边界加固** — `layered_memory.py:read_static_memory_files` glob 加 PermissionError/OSError 捕获
3. **E2E 回归测试** — 新增 23 例：真建会话、真发对话、查所有 admin 端点
4. **多 worker 并发测试** — 新增 2 例：20 线程并发原子写不损坏

## 审计结论

**opencode 报告这次没虚高。** 四条线交叉验证一致：

- 健康检查：ok, module_errors null
- hook-lifecycle: 20 条真记录，last=memory_distill
- memory-quality: total_recalls=1, credibility_score=40.0（甚至比报告好）
- overview: 12 对话/64 事件（E2E 测试新增）
- 全量 152 例测试全绿

**但有一处不符：报告称"已提交"，实际改动未提交。** 小马仔审计发现后补提交 `2944ede`。

## 踩过的坑

- opencode 模式再次验证：虽然这次没虚高，但"报告已提交但实际未提交"是典型粗心。交接铁律"亲手真打活系统复核"再次证明价值。
- git diff 确认改动严格限制在 modules/agent/backend/ + backend/tests/，符合模块隔离规则。

## 剩余风险

- hook_runs.json 当前上限 200 条，高频对话可能触发写竞争，建议后续加按时间/容量二级截断
- 静态记忆 60s TTL 硬编码，更新后最多 60s 才生效
- 异常降级时丢失诊断信息（所有 hook/record_event/DB 操作出错静默）
