---
name: "工具台反馈-20260703-071918-codex-opencode-mcp-audit-20260703-r2-审计 opencode MCP/SDK 最小可用性、只读 prompt "
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-opencode-mcp-audit-20260703-r2"
created: "2026-07-03T07:19:18.075219+00:00"
---

# MCP 使用反馈

## 任务

审计 opencode MCP/SDK 最小可用性、只读 prompt 行为、dirty worktree patch 归因风险

## 顺畅度

- 评分：4/5
- 体感：整体顺畅：gateway/status、sdk_smoke、sdk_prompt 都能直接给出结构化证据，足够做最小可用性审计。

## 本次用到的工具

brief, plan_task, worktree_guard, opencode_gateway_status, opencode_sdk_smoke, opencode_sdk_prompt, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

opencode_sdk_prompt 的 agent 参数传入未注册值时只返回 UnknownError/ref，缺少可读校验；finish_task 默认边界检查没有接收 allowed_prefixes/forbidden_prefixes，容易与前面严格 worktree_guard 结论不一致；当前同分支并发写入时，工具缺少 git status 前后差分归因摘要。

## 缺少的工具 / 能力

需要一个 read-only opencode prompt 模式或 dry-run capability，明确禁止 patch/file effects；需要 status_snapshot/status_diff 工具，把两次 git status 做结构化差分并标注新增/消失/既有；需要 opencode log_tail 脱敏开关或安全摘要。

## 升级建议

opencode_sdk_prompt 增加 agent 枚举校验；返回 patch part 时标注 patch 来源是 existing dirty snapshot 还是本轮新增；opencode_gateway_status 默认隐藏 session_id/thread_id/remote URL/commit hash 等敏感 metadata；finish_task 支持 allowed_prefixes/forbidden_prefixes 参数并在报告里沿用严格边界。

## 建议移除或合并的工具

无

## 其他备注

本轮结论：opencode SDK/MCP 最小可用，但不建议在当前脏工作区直接作为会改文件的执行代理；适合在独立干净 worktree、设置密码、日志脱敏、强制边界守卫后继续试用。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 712,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 497,
    "error": 0,
    "avg_duration_seconds": 0.023
  },
  {
    "tool": "code_explore",
    "calls": 322,
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
    "calls": 279,
    "error": 2,
    "avg_duration_seconds": 3.672
  },
  {
    "tool": "call_capability",
    "calls": 265,
    "error": 12,
    "avg_duration_seconds": 0.689
  },
  {
    "tool": "worktree_guard",
    "calls": 265,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 249,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 216,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "probe",
    "calls": 208,
    "error": 2,
    "avg_duration_seconds": 0.524
  }
]
```
