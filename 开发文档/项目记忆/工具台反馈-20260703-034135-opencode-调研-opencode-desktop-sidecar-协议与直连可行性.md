---
name: "工具台反馈-20260703-034135-opencode-调研 OpenCode Desktop sidecar 协议与直连可行性"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "opencode"
created: "2026-07-03T03:41:35.216355+00:00"
---

# MCP 使用反馈

## 任务

调研 OpenCode Desktop sidecar 协议与直连可行性

## 顺畅度

- 评分：5/5
- 体感：非常顺畅。信里给的验证命令直接可用, asar 工具配合 rg/ps/curl/lsof 快速定位了认证机制全过程。

## 本次用到的工具

bash, codegraph_node, web_read, read, mailbox_create_delivery_bundle, mailbox_check_delivery_bundle, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

无

## 缺少的工具 / 能力

无

## 升级建议

无

## 建议移除或合并的工具

无

## 其他备注

调研任务无需 plan_task 和 finish_task, 直接按 验证命令 → 源码分析 → 结论 → 五件套 的顺序走更高效。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 442,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 310,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 270,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 228,
    "error": 0,
    "avg_duration_seconds": 0.321
  },
  {
    "tool": "db_schema",
    "calls": 161,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 156,
    "error": 1,
    "avg_duration_seconds": 2.955
  },
  {
    "tool": "worktree_guard",
    "calls": 156,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 139,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "probe",
    "calls": 126,
    "error": 0,
    "avg_duration_seconds": 0.483
  },
  {
    "tool": "plan_task",
    "calls": 110,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
