---
name: "工具台反馈-20260704-131718-codex-full-module-gap-audit-全模块能力缺口与重复造轮子只读总审计，输出总审计报告"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-full-module-gap-audit"
created: "2026-07-04T13:17:18.587599+00:00"
---

# MCP 使用反馈

## 任务

全模块能力缺口与重复造轮子只读总审计，输出总审计报告

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，release_gate preflight 和 capability drift 信息很适合审计报告引用。

## 本次用到的工具

brief,plan_task,worktree_guard,capabilities,release_gate,db_schema,routes,tail_log,code_explore,db_reverse_audit,finish_task,memory_write,mcp_feedback

## 卡点 / 不顺手的地方

capabilities 输出过长且难以直接汇总模块级数量；worktree_guard 在并行总攻工作区下会把大量非本轮变更都标为 new，需要人工解释。

## 缺少的工具 / 能力

希望有只读审计专用 summary 工具：按模块输出 manifest/README/sandbox/capability/file-access 的 compact JSON。

## 升级建议

release_gate 可额外输出 markdown-ready 摘要；db_reverse_audit 可在 include_code_references=false 时不要报 data_without_code_reference，减少误导。

## 建议移除或合并的工具

无

## 其他备注

本轮按调研信写报告、memory_write、mcp_feedback；未修改产品代码。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 414,
    "error": 0,
    "avg_duration_seconds": 0.148
  },
  {
    "tool": "code_explore",
    "calls": 253,
    "error": 0,
    "avg_duration_seconds": 0.342
  },
  {
    "tool": "probe",
    "calls": 167,
    "error": 4,
    "avg_duration_seconds": 0.325
  },
  {
    "tool": "worktree_guard",
    "calls": 167,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 126,
    "error": 0,
    "avg_duration_seconds": 0.759
  },
  {
    "tool": "plan_task",
    "calls": 125,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "sql",
    "calls": 115,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "call_capability",
    "calls": 114,
    "error": 5,
    "avg_duration_seconds": 0.29
  },
  {
    "tool": "code_impact",
    "calls": 113,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "db_schema",
    "calls": 85,
    "error": 0,
    "avg_duration_seconds": 0.032
  }
]
```
