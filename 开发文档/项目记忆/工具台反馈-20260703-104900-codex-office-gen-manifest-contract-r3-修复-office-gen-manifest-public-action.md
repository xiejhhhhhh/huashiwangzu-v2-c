---
name: "工具台反馈-20260703-104900-codex-office-gen-manifest-contract-r3-修复 office-gen manifest public_action"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-office-gen-manifest-contract-r3"
created: "2026-07-03T10:49:00.151662+00:00"
---

# MCP 使用反馈

## 任务

修复 office-gen manifest public_actions 参数元数据漂移，只改 office-gen manifest。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/capabilities/code_node 对定位 manifest 漂移很快。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, memory_search, run_test, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

lint 工具对实际存在的 modules/office-gen/backend、tests、sandbox 目录误报文件不存在；probe /api/modules/capabilities 输出过长且无法直接按 module 过滤。

## 缺少的工具 / 能力

希望 probe 或 capabilities 增加 live registry 按 module/action 过滤，便于验证运行时能力元数据。

## 升级建议

修复 lint 目录路径校验；给 probe 的大 JSON 返回增加 jq/filter 参数或内置 module capability filter。

## 建议移除或合并的工具

无

## 其他备注

worktree_guard 能及时暴露并行 dirty 文件，适合这类多 worker 任务。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1068,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 598,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 433,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 411,
    "error": 17,
    "avg_duration_seconds": 0.759
  },
  {
    "tool": "probe",
    "calls": 408,
    "error": 3,
    "avg_duration_seconds": 0.443
  },
  {
    "tool": "sql",
    "calls": 397,
    "error": 16,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 375,
    "error": 2,
    "avg_duration_seconds": 3.158
  },
  {
    "tool": "code_impact",
    "calls": 372,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 350,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 300,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
