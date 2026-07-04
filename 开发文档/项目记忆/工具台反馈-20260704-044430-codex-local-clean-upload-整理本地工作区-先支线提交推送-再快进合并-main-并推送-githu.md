---
name: "工具台反馈-20260704-044430-codex-local-clean-upload-整理本地工作区，先支线提交推送，再快进合并 main 并推送 GitHu"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-local-clean-upload"
created: "2026-07-04T04:44:30.019261+00:00"
---

# MCP 使用反馈

## 任务

整理本地工作区，先支线提交推送，再快进合并 main 并推送 GitHub。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/worktree_guard/lint/run_test/finish_task 对收口很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, probe, release_gate, lint, run_test, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 会重新跑合并 test_targets，导致与前面分组 run_test 有重复；Git 输出中文路径被转义，人工阅读不便。

## 缺少的工具 / 能力

可考虑提供 Git 收口专用工具：自动汇总 dirty、敏感扫描、分支提交、push、fast-forward main、最终状态报告。

## 升级建议

finish_task 可支持声明已完成的测试结果并选择不重复跑；worktree_guard/Git 工具可增加 quotePath=false 风格输出。

## 建议移除或合并的工具

无

## 其他备注

用户要求下载走 127.0.0.1:4780；本次 push 已显式设置 HTTP_PROXY/HTTPS_PROXY。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1466,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "probe",
    "calls": 707,
    "error": 8,
    "avg_duration_seconds": 0.436
  },
  {
    "tool": "code_explore",
    "calls": 697,
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
    "calls": 590,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 583,
    "error": 18,
    "avg_duration_seconds": 0.623
  },
  {
    "tool": "worktree_guard",
    "calls": 547,
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
