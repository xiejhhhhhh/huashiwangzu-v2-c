---
name: "工具台反馈-20260703-115256-codex-r5-mcp-baseline-d-R5 第一阶段任务 D：为项目 MCP worktree_guard/f"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-r5-mcp-baseline-d"
created: "2026-07-03T11:52:56.447762+00:00"
---

# MCP 使用反馈

## 任务

R5 第一阶段任务 D：为项目 MCP worktree_guard/finish_task 增加 baseline 归因参数和测试。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和 lint/run_test 很适合这个工具台自修任务。

## 本次用到的工具

brief,plan_task,worktree_guard,code_explore,code_node,code_impact,lint,run_test,memory_write,mcp_feedback

## 卡点 / 不顺手的地方

当前 MCP server 是开工时加载的旧 schema，本轮新增的 baseline 参数需要重启会话后才能在 live tool schema 中使用。并行 worker 在同一文件出现 response shaping diff，最终 diff 需要人工按任务归因看。

## 缺少的工具 / 能力

无

## 升级建议

worktree_guard baseline 能力上线后，可在主会话创建子代理时自动记录 baseline_status_json 并传给 finish_task。

## 建议移除或合并的工具

无

## 其他备注

未碰 knowledge 模块；检测到 knowledge dirty 属于并行 worker。

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
    "calls": 626,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 499,
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
    "calls": 412,
    "error": 2,
    "avg_duration_seconds": 3.279
  },
  {
    "tool": "code_impact",
    "calls": 402,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 390,
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
