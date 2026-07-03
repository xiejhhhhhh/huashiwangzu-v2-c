---
name: "工具台反馈-20260703-115205-codex-r5-knowledge-archive-b-R5 knowledge 历史 failed 队列 guarded ar"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-r5-knowledge-archive-b"
created: "2026-07-03T11:52:05.986192+00:00"
---

# MCP 使用反馈

## 任务

R5 knowledge 历史 failed 队列 guarded archive 收口

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和工具台足够快地定位了 pipeline debt apply 入口与影响面。

## 本次用到的工具

brief,plan_task,worktree_guard,code_explore,code_node,code_impact,routes,capabilities,db_schema,sql,lint,run_test,call_capability,probe,tail_log,finish_task,memory_write

## 卡点 / 不顺手的地方

并行 worker 中途产生 dirty 文件，finish_task 的边界检查只能给全局 dirty 结果，无法区分本 agent 本轮触碰文件。

## 缺少的工具 / 能力

缺一个按本会话写入/mtime/agent 标记区分 touched files 的边界报告工具；现在需要人工说明并行改动。

## 升级建议

finish_task/worktree_guard 可支持 baseline snapshot id，对比开工时状态后只报告本 agent 新增 dirty。

## 建议移除或合并的工具

无

## 其他备注

本次未批量 apply 生产数据，只做 dry-run/只读 SQL/能力验证。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1137,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 623,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 497,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 484,
    "error": 6,
    "avg_duration_seconds": 0.448
  },
  {
    "tool": "code_explore",
    "calls": 471,
    "error": 0,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "call_capability",
    "calls": 458,
    "error": 17,
    "avg_duration_seconds": 0.709
  },
  {
    "tool": "run_test",
    "calls": 409,
    "error": 2,
    "avg_duration_seconds": 3.258
  },
  {
    "tool": "code_impact",
    "calls": 402,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 389,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 340,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
