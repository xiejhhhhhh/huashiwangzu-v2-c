---
name: "工具台反馈-20260702-165443-knowledge-live-chain-r4-专项核实并补修知识库完整链路，覆盖生命周期竞态、parser-empty"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "knowledge-live-chain-r4"
created: "2026-07-02T16:54:43.932327+00:00"
---

# MCP 使用反馈

## 任务

专项核实并补修知识库完整链路，覆盖生命周期竞态、parser-empty 降级、诊断 schema 热迁移锁竞争。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph + SQL + tail_log 很快定位到活系统竞态。

## 本次用到的工具

brief,plan_task,worktree_guard,code_explore,code_node,code_impact,routes,capabilities,db_schema,sql,probe,tail_log,run_test,finish_task,memory_write,mcp_feedback

## 卡点 / 不顺手的地方

lint 工具一次传多个路径会被当成单个文件；finish_task/worktree_guard 在多 agent 大量未提交改动时会全局报边界失败，需要人工辨别本轮实际改动。

## 缺少的工具 / 能力

希望有按 agent/时间窗口过滤 git dirty 的工具，或 finish_task 支持 declared_touched_files，只对本轮文件做边界判断。

## 升级建议

db_schema/SQL 之外可增加 migration-lock-risk 检查，识别 ALTER TABLE IF NOT EXISTS 热执行风险；tail_log 可以自动展开同一 request/task 的完整 traceback。

## 建议移除或合并的工具

无

## 其他备注

run_test 对单目标很好用；复杂多目标和 ruff 多路径仍然直接 shell 更稳。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 389,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 269,
    "error": 0,
    "avg_duration_seconds": 0.016
  },
  {
    "tool": "sql",
    "calls": 197,
    "error": 8,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_explore",
    "calls": 189,
    "error": 0,
    "avg_duration_seconds": 0.311
  },
  {
    "tool": "code_impact",
    "calls": 123,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "worktree_guard",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 2.258
  },
  {
    "tool": "db_schema",
    "calls": 114,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 99,
    "error": 0,
    "avg_duration_seconds": 0.534
  },
  {
    "tool": "plan_task",
    "calls": 84,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
