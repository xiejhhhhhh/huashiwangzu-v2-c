---
name: "工具台反馈-20260703-113257-codex-readonly-media-cost-research-只读调研图片/视频分析如何用本地算法降低 VLM 成本并给出落地架构建议"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-readonly-media-cost-research"
created: "2026-07-03T11:32:57.263615+00:00"
---

# MCP 使用反馈

## 任务

只读调研图片/视频分析如何用本地算法降低 VLM 成本并给出落地架构建议

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/code_explore/capabilities/db_schema/finish_task 能快速定位现状。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, capabilities, db_schema, finish_task, memory_write

## 卡点 / 不顺手的地方

capabilities 全量输出很长且中间截断，不适合精确枚举媒体模块；code_explore 预算提示只有 2 次，后续仍需回到 shell 阅读。

## 缺少的工具 / 能力

希望 capabilities 支持 module 前缀/关键词过滤，例如 media-* 或 action contains video。

## 升级建议

给 investigation 类型的 plan_task 区分故障排查和架构调研，避免强制建议 tail_log。

## 建议移除或合并的工具

无

## 其他备注

本次按只读调研执行，未改产品代码。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1121,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 619,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 487,
    "error": 25,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "probe",
    "calls": 483,
    "error": 6,
    "avg_duration_seconds": 0.448
  },
  {
    "tool": "code_explore",
    "calls": 463,
    "error": 0,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "call_capability",
    "calls": 453,
    "error": 17,
    "avg_duration_seconds": 0.713
  },
  {
    "tool": "run_test",
    "calls": 403,
    "error": 2,
    "avg_duration_seconds": 3.294
  },
  {
    "tool": "code_impact",
    "calls": 394,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 380,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 333,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
