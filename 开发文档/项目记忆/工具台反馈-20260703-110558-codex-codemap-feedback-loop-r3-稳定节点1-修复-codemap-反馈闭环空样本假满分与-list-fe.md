---
name: "工具台反馈-20260703-110558-codex-codemap-feedback-loop-r3-稳定节点1：修复 codemap 反馈闭环空样本假满分与 list_fe"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-codemap-feedback-loop-r3"
created: "2026-07-03T11:05:58.088842+00:00"
---

# MCP 使用反馈

## 任务

稳定节点1：修复 codemap 反馈闭环空样本假满分与 list_feedback 空态不可见

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和活栈探针定位很快。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, probe, call_capability, sql, run_test, lint, tail_log, memory_write

## 卡点 / 不顺手的地方

lint 工具传目录时误报文件不存在，只能改传具体 Python 文件；tail_log(module=backend) 返回空，需要手动 tail backend/logs/backend.log。

## 缺少的工具 / 能力

希望 run_test/lint 对模块目录有原生命名支持；希望提供安全的测试数据 cleanup helper 或只读/限定 DELETE 工具。

## 升级建议

lint 可接受目录并自动展开 Python 文件；tail_log 对 backend 参数应等价于默认后端日志。

## 建议移除或合并的工具

无

## 其他备注

工作区有其他 agent 的非 codemap dirty 文件，worktree_guard 会整体失败；本节点用 git diff -- modules/codemap 额外确认本轮范围。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1100,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 612,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 444,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 441,
    "error": 5,
    "avg_duration_seconds": 0.445
  },
  {
    "tool": "sql",
    "calls": 441,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 427,
    "error": 17,
    "avg_duration_seconds": 0.74
  },
  {
    "tool": "run_test",
    "calls": 393,
    "error": 2,
    "avg_duration_seconds": 3.229
  },
  {
    "tool": "code_impact",
    "calls": 385,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 368,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 316,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
