---
name: "工具台反馈-20260703-072949-codex-media-intelligence-architecture-20260703-r2-新增 media-intelligence 模块骨架，落地本地算法-小模"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-media-intelligence-architecture-20260703-r2"
created: "2026-07-03T07:29:49.258005+00:00"
---

# MCP 使用反馈

## 任务

新增 media-intelligence 模块骨架，落地本地算法-小模型-VLM 分层流水线契约、provider registry、统一分析 schema、8 个能力声明、轻量前端和 sandbox 验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅：brief/plan_task/worktree_guard/code_explore/capabilities/lint/run_test/finish_task 能覆盖从开工到验收的主流程。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, tail_log, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

共享工作区多 worker 并发 dirty 会让 worktree_guard/finish_task 总状态 false，虽然本任务 forbidden_hits 为 0；需要人工阅读输出区分本任务越界与他人并发改动。

## 缺少的工具 / 能力

缺少可写 agent_board heartbeat 工具；只搜到 agent_board_snapshot，阶段节点只能用 memory_write 留痕。

## 升级建议

finish_task 可以支持 allowed_prefixes 附加 `开发文档/项目记忆/` 并在报告中单独标注 forbidden_hits=0 的模块任务为边界通过但工作区有外部并发改动。

## 建议移除或合并的工具

无

## 其他备注

新模块 route/capability 的活系统验证依赖后端重启/manifest 重载；当前已用 manifest scan 和 sandbox pytest 验证契约。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 729,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 506,
    "error": 0,
    "avg_duration_seconds": 0.024
  },
  {
    "tool": "code_explore",
    "calls": 326,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 301,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 290,
    "error": 16,
    "avg_duration_seconds": 0.688
  },
  {
    "tool": "run_test",
    "calls": 284,
    "error": 2,
    "avg_duration_seconds": 3.615
  },
  {
    "tool": "worktree_guard",
    "calls": 274,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 255,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 236,
    "error": 2,
    "avg_duration_seconds": 0.503
  },
  {
    "tool": "db_schema",
    "calls": 225,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
