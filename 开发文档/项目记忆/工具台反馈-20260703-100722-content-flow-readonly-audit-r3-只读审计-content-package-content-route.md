---
name: "工具台反馈-20260703-100722-content-flow-readonly-audit-r3-只读审计 Content Package / content route"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "content-flow-readonly-audit-r3"
created: "2026-07-03T10:07:22.486642+00:00"
---

# MCP 使用反馈

## 任务

只读审计 Content Package / content router / export_service / artifact_service 链路，验证 target_file_id、get_file_content 空内容语义和 check_file_access 覆盖。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和 routes/db_schema 能快速定位链路和契约。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, db_reverse_audit, probe, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 初始返回干净，但 finish_task 后 git 视图显示已有 dirty 文件，两个工具的工作区口径不一致，容易误判只读审计是否污染了文件。probe /api/modules/capabilities 输出过长且截断，筛选 content 能力需要人工摘取。

## 缺少的工具 / 能力

希望 probe/capabilities 支持服务端过滤 module=content 并只返回匹配项；希望 worktree_guard 与 finish_task 使用完全一致的 git dirty 检测口径。

## 升级建议

给 investigation/readonly 模式增加“禁止调用写入型能力”的提示或 dry-run guard；capability 列表工具支持运行时 registry 过滤，不只扫 manifest。

## 建议移除或合并的工具

无

## 其他备注

未触碰 data/uploads；未调用 content:get_file_content/publish/export 等会写库或写文件的能力。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1009,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 579,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 405,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 393,
    "error": 17,
    "avg_duration_seconds": 0.78
  },
  {
    "tool": "probe",
    "calls": 367,
    "error": 3,
    "avg_duration_seconds": 0.457
  },
  {
    "tool": "sql",
    "calls": 367,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 355,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 340,
    "error": 2,
    "avg_duration_seconds": 3.204
  },
  {
    "tool": "worktree_guard",
    "calls": 330,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 278,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
