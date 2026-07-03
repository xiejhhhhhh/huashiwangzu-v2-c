---
name: "工具台反馈-20260703-105005-codex-douyin-codemap-imagegen-flow-audit-r3-只读审计 douyin-delivery、codemap_feedbac"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-douyin-codemap-imagegen-flow-audit-r3"
created: "2026-07-03T10:50:05.655121+00:00"
---

# MCP 使用反馈

## 任务

只读审计 douyin-delivery、codemap_feedback、imagegen_records 三条疑似空链路并输出 P0/P1/P2 结论

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，db_reverse_audit 对空表初筛很有效，routes/capabilities/probe 组合能快速确认活栈状态。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, routes, capabilities, db_schema, db_reverse_audit, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

缺少只读 SQL MCP 工具，样本行/owner 分布需要通过本地 Python 只读查询完成；tail_log 返回空但没有说明日志文件为空还是目标模块无日志。

## 缺少的工具 / 能力

建议增加 read_only_sql 或 db_sample_rows 工具，支持限制 SELECT、自动脱敏和表样本；tail_log 可返回日志路径和空日志原因。

## 升级建议

db_reverse_audit 可附带 owner_id 分布、最近样本行和当前登录用户 id，减少额外查询；capabilities 可标注 read/write/costly 便于只读审计避开写入/付费能力。

## 建议移除或合并的工具

无

## 其他备注

审计期间工作区出现其他 worker 的未提交改动；本 agent 仅写入要求的项目记忆和工具台反馈。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1069,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 600,
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
    "tool": "probe",
    "calls": 412,
    "error": 3,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "call_capability",
    "calls": 411,
    "error": 17,
    "avg_duration_seconds": 0.759
  },
  {
    "tool": "sql",
    "calls": 406,
    "error": 18,
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
    "calls": 354,
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
