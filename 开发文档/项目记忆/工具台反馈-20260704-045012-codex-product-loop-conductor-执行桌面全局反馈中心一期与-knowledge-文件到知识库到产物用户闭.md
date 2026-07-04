---
name: "工具台反馈-20260704-045012-codex-product-loop-conductor-执行桌面全局反馈中心一期与 Knowledge 文件到知识库到产物用户闭"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-product-loop-conductor"
created: "2026-07-04T04:50:12.224287+00:00"
---

# MCP 使用反馈

## 任务

执行桌面全局反馈中心一期与 Knowledge 文件到知识库到产物用户闭环一期，并做多子代理最终验收。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，probe/call_capability/finish_task 对活栈验收和边界收口很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, routes, capabilities, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的 forbidden_prefixes 不能像 worktree_guard 一样显式传入，因此它适合看当前 dirty 边界，但不能直接表达用户额外禁止路径；历史提交边界仍需要 git show/log 人工交叉核对。

## 缺少的工具 / 能力

缺少一个按提交范围审计 allowed/forbidden boundary 的工具，例如检查 HEAD~N..HEAD 或指定 commit 列表是否触碰禁止路径。

## 升级建议

建议 finish_task 增加 forbidden_prefixes 参数，并增加 commit_range_boundary_check，区分当前 dirty、已提交未推送、已推送历史三类风险。

## 建议移除或合并的工具

无

## 其他备注

本轮多子代理复核有效发现了 cancelled 文案和 Knowledge 二期风险；当前外部上传线已把 main/origin/main 对齐。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1483,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "probe",
    "calls": 727,
    "error": 8,
    "avg_duration_seconds": 0.431
  },
  {
    "tool": "code_explore",
    "calls": 701,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "lint",
    "calls": 681,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "sql",
    "calls": 591,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 588,
    "error": 18,
    "avg_duration_seconds": 0.62
  },
  {
    "tool": "worktree_guard",
    "calls": 553,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 504,
    "error": 3,
    "avg_duration_seconds": 4.424
  },
  {
    "tool": "code_impact",
    "calls": 493,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 443,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
