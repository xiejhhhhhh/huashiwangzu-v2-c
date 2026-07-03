---
name: "工具台反馈-20260703-111130-codex-douyin-codemap-imagegen-flow-audit-r3-稳定节点2：验证 image-gen placeholder 生成会写入"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-douyin-codemap-imagegen-flow-audit-r3"
created: "2026-07-03T11:11:30.935909+00:00"
---

# MCP 使用反馈

## 任务

稳定节点2：验证 image-gen placeholder 生成会写入 imagegen_records 且 history 可读，并清理测试数据

## 顺畅度

- 评分：4/5
- 体感：活栈 HTTP + 直接清理测试记录整体顺畅，工具台落盘通过组件兜底完成。

## 本次用到的工具

git status, pytest, ruff, live HTTP generate/history, DB/file cleanup, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

image-gen 没有模块内 cleanup 能力，测试产物清理需要直接删 imagegen_records、framework_file_items 和物理文件。

## 缺少的工具 / 能力

建议 image-gen 增加测试 marker cleanup 或 dev_toolkit 提供 generated artifact cleanup helper。

## 升级建议

db_reverse_audit 可对空记录表提供“低成本可清理 probe 建议”，区分代码断链和当前库无历史数据。

## 建议移除或合并的工具

无

## 其他备注

本节点未改 image-gen 代码；真实付费 provider 未触发。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1112,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 614,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 450,
    "error": 5,
    "avg_duration_seconds": 0.449
  },
  {
    "tool": "code_explore",
    "calls": 446,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "call_capability",
    "calls": 444,
    "error": 17,
    "avg_duration_seconds": 0.722
  },
  {
    "tool": "sql",
    "calls": 442,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
  },
  {
    "tool": "code_impact",
    "calls": 391,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 370,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 317,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
