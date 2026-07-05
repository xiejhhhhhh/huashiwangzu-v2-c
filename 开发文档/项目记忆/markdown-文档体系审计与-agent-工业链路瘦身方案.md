---
name: "Markdown 文档体系审计与 Agent 工业链路瘦身方案"
type: "task"
tags: [docs, markdown, agent-handoff, documentation-architecture, audit]
agent: "codex"
created: "2026-07-05T09:02:55.110894+00:00"
---

Agent: codex。任务：只读审计全项目 Markdown、开发文档与模块 README，并核实关键文档陈述与代码/能力现实是否一致。结论：970 个 Markdown、约 6.7 万行，其中开发文档/项目记忆 894 个、约 83.6% 体积，是最大噪音源；主入口 README/三类开发 README 基本清楚，但缺 agent_handoff/CURRENT_STATE/CONTRACTS/ACCEPTANCE 这类工业链路入口；dev_toolkit/README 464 行偏工具百科；knowledge_video_analysis_system_plan.md 1334 行需拆分；模块 README 全存在且验收矩阵 35/35，但 agent、knowledge、excel-engine、memory 有局部陈旧或误导陈述。核实：capability_contract_diff 通过，manifest/live/source public capabilities 189 对齐；routes 证实 /api/modules/call body 为 target_module/action/parameters；db_schema 证实表前缀含 agent/kb/memory/excel/framework 等；release_gate preflight 显示健康/队列/能力/README 矩阵通过，但测试数据污染仍是 BLOCKER。建议：先建立 agent_handoff 当前状态/契约/验收/故障诊断入口；项目记忆分层并默认只加载 active/current/decision/contract；模块 README 改为 80-120 行 handoff card + generated public_actions + validation matrix；历史/审计/执行信归档不作当前规范入口。
