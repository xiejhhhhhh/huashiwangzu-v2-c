---
name: "工具台反馈-20260703-071411-codex-workflow-sweep-20260703-r2-modules/scheduler r2 sweep: hardened"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-workflow-sweep-20260703-r2"
created: "2026-07-03T07:14:11.586734+00:00"
---

# MCP 使用反馈

## 任务

modules/scheduler r2 sweep: hardened scheduler validation, recurrence, cancel semantics, runtime route, manifest contract, sandbox coverage.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/routes/capabilities/db_schema/lint/run_test/probe/finish_task 串起来能覆盖这个小模块。

## 本次用到的工具

brief,plan_task,worktree_guard,agent_board_claim,agent_board_heartbeat,code_explore,code_node,code_impact,routes,capabilities,db_schema,lint,run_test,probe,call_capability,tail_log,finish_task,memory_write,mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的 boundary_check 在共享并行工作区会把其他 worker 的脏文件合并进 success:false，虽然 forbidden_hits=0；需要人工读细节判断。

## 缺少的工具 / 能力

缺少一个按 agent/task_id 标记本次触碰文件的 scoped boundary summary，可直接区分本 worker 改动与共享工作区已有脏文件。

## 升级建议

finish_task 可以支持 allowed_prefixes 额外包含 开发文档/项目记忆，并在输出里单独给出 current_agent_changed_files/scoped_status。

## 建议移除或合并的工具

无

## 其他备注

活系统未重启以免干扰并行 worker；新代码严格语义通过 in-process/tests 验证，活系统只做旧进程上的 create/list/cancel 链路和清理。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 708,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 489,
    "error": 0,
    "avg_duration_seconds": 0.022
  },
  {
    "tool": "code_explore",
    "calls": 321,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 301,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 275,
    "error": 2,
    "avg_duration_seconds": 3.717
  },
  {
    "tool": "worktree_guard",
    "calls": 259,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 255,
    "error": 12,
    "avg_duration_seconds": 0.662
  },
  {
    "tool": "code_impact",
    "calls": 247,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 214,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 204,
    "error": 2,
    "avg_duration_seconds": 0.529
  }
]
```
