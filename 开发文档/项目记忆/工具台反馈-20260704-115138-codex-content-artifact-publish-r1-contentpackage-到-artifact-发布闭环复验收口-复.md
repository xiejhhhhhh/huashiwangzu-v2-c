---
name: "工具台反馈-20260704-115138-codex-content-artifact-publish-r1-ContentPackage 到 Artifact 发布闭环复验收口：复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T11:51:38.188715+00:00"
---

# MCP 使用反馈

## 任务

ContentPackage 到 Artifact 发布闭环复验收口：复核实现、跑必需测试、打活栈 content:write_ir -> content:publish -> REST publish -> file download，并清理探针数据。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/finish_task 对接手已有实现很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, probe, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

工作区并行任务很多，worktree_guard 需要手动维护 baseline_paths；子代理旧任务通知混入当前任务，容易造成上下文噪声。

## 缺少的工具 / 能力

缺少一个按当前 turn 自动冻结 baseline 并在 finish_task 复用的轻量工具。

## 升级建议

建议 worktree_guard/finish_task 支持保存并引用本轮 baseline id；子代理通知最好带任务标题过滤或可静音非当前执行信通知。

## 建议移除或合并的工具

无

## 其他备注

根目录直接跑 backend/.venv/bin/python pytest 时不会自动加载 backend/.env，需按 README 在 backend cwd 跑，或显式加载 backend/.env。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 294,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 180,
    "error": 0,
    "avg_duration_seconds": 0.336
  },
  {
    "tool": "worktree_guard",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 118,
    "error": 3,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "call_capability",
    "calls": 100,
    "error": 5,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "sql",
    "calls": 99,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 94,
    "error": 0,
    "avg_duration_seconds": 0.748
  },
  {
    "tool": "plan_task",
    "calls": 92,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 90,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "run_test",
    "calls": 59,
    "error": 0,
    "avg_duration_seconds": 4.982
  }
]
```
