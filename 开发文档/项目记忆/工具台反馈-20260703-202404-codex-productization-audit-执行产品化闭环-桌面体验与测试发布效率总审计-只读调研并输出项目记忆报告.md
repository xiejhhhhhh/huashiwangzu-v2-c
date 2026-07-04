---
name: "工具台反馈-20260703-202404-codex-productization-audit-执行产品化闭环、桌面体验与测试发布效率总审计，只读调研并输出项目记忆报告"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-productization-audit"
created: "2026-07-03T20:24:04.080294+00:00"
---

# MCP 使用反馈

## 任务

执行产品化闭环、桌面体验与测试发布效率总审计，只读调研并输出项目记忆报告。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，工具台对只读审计、活栈探测、release gate 和模块 sandbox 的组合很有效。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, routes, capabilities, db_schema, probe, call_capability, release_gate, module_sandbox_matrix, memory_search, tail_log, tool_job_submit, tool_job_status, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 在并行多 agent 工作区里很容易把其他 agent 新增的未跟踪文件也算成本轮越界；如果没有开工 baseline JSON，收工时需要人工解释。

## 缺少的工具 / 能力

希望有一个 read-only audit 模式的 finish_task，可显式声明本轮只允许写项目记忆，并把其他未跟踪源码变更归为 parallel/unknown 而不是直接混入本轮。

## 升级建议

worktree_guard/finish_task 可以支持“本轮产物清单”参数，用于在 dirty 工作区里只核对指定报告、记忆、反馈文件是否越界。

## 建议移除或合并的工具

无

## 其他备注

本轮 release_gate(full, skip_ui=true) 返回 PASS_WITH_DEBT 且 release_safe=true；由于 UI 跳过，报告中已明确不能当 clean release 使用。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1443,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "probe",
    "calls": 683,
    "error": 8,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "lint",
    "calls": 675,
    "error": 0,
    "avg_duration_seconds": 0.032
  },
  {
    "tool": "code_explore",
    "calls": 674,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 587,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 539,
    "error": 18,
    "avg_duration_seconds": 0.652
  },
  {
    "tool": "worktree_guard",
    "calls": 531,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 487,
    "error": 3,
    "avg_duration_seconds": 4.456
  },
  {
    "tool": "code_impact",
    "calls": 481,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 435,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
