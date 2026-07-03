---
name: "工具台反馈-20260703-071528-codex-conductor-sweep-20260703-r2-opencode SDK 最小冒烟与媒体智能架构决策落盘"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:15:28.629548+00:00"
---

# MCP 使用反馈

## 任务

opencode SDK 最小冒烟与媒体智能架构决策落盘

## 顺畅度

- 评分：3/5
- 体感：SDK 冒烟可用，但在共享脏工作区中返回 patch files，容易把已有 diff 误归因到本次会话。

## 本次用到的工具

opencode_gateway_status, opencode_sdk_smoke, memory_write

## 卡点 / 不顺手的地方

opencode_sdk_smoke 提示不要改文件仍返回 patch 列表；需要干净 worktree 或工具侧显示 patch 是否为本次实际写入。

## 缺少的工具 / 能力

opencode SDK dry-run/readonly 模式、自动隔离临时 worktree 冒烟、会话实际写文件审计。

## 升级建议

为 opencode_sdk_prompt/smoke 增加 readonly=true 或 pre/post git diff hash 对比，返回 only_new_changes 字段，避免共享工作区误判。

## 建议移除或合并的工具

无

## 其他备注

本轮暂不把 opencode 用作写代码代理，只确认网关可达与 SDK 最小 prompt 通。

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
    "calls": 491,
    "error": 0,
    "avg_duration_seconds": 0.023
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
    "calls": 277,
    "error": 2,
    "avg_duration_seconds": 3.693
  },
  {
    "tool": "call_capability",
    "calls": 260,
    "error": 12,
    "avg_duration_seconds": 0.697
  },
  {
    "tool": "worktree_guard",
    "calls": 260,
    "error": 0,
    "avg_duration_seconds": 0.031
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
    "calls": 205,
    "error": 2,
    "avg_duration_seconds": 0.527
  }
]
```
