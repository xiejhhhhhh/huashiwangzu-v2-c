---
name: "工具台反馈-20260703-072955-codex-conductor-sweep-20260703-r2-主会话验收并提交 douyin-delivery r2 投递契约修复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:29:55.442049+00:00"
---

# MCP 使用反馈

## 任务

主会话验收并提交 douyin-delivery r2 投递契约修复

## 顺畅度

- 评分：4/5
- 体感：probe/call_capability 能较快打通真实 CRUD 和能力调用，适合这类业务模块验收。

## 本次用到的工具

code_node,routes,capabilities,db_schema,probe,call_capability,db_reverse_audit,memory_write,mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 在并发 worker dirty 很多时会显示 forbidden hit，不适合作为单模块归因的唯一结论；需要结合 git diff --name-only 和 staging 清单。

## 缺少的工具 / 能力

希望工具台提供按 marker 自动创建/清理/核验的事务式验收助手。

## 升级建议

为 worktree_guard 增加 baseline 参数，可只评估某一子代理开始后新增文件；为 probe 增加从上一次响应提取 id 的链式能力。

## 建议移除或合并的工具

无

## 其他备注

本次测试数据已通过 cleanup_marked_data 清理。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 731,
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
    "calls": 327,
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
