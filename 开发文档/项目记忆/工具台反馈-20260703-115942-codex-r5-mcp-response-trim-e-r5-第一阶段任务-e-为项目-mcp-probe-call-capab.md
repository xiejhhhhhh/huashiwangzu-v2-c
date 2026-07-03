---
name: "工具台反馈-20260703-115942-codex-r5-mcp-response-trim-e-R5 第一阶段任务 E：为项目 MCP probe/call_capab"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-r5-mcp-response-trim-e"
created: "2026-07-03T11:59:42.979004+00:00"
---

# MCP 使用反馈

## 任务

R5 第一阶段任务 E：为项目 MCP probe/call_capability 增加 selector/max_items/max_bytes 大响应裁剪

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph、plan_task、worktree_guard、lint、run_test、finish_task 都能支撑本次工具台改造。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

当前会话中的 MCP schema 不会热更新，新增 probe/call_capability 参数必须重启会话后才能用 MCP 工具本身验证；lint(path='dev_toolkit') 不支持目录但报文件不存在，容易误导。

## 缺少的工具 / 能力

希望提供一个 reload/self-probe 当前工作区 MCP server 的工具，或支持对未重启 schema 的本地 tool call dry-run。

## 升级建议

lint 工具支持目录路径；finish_task 可以在全局任务里也把 outside_allowed_count 计入醒目风险但不直接失败；工具 schema 变更后给出重启提示。

## 建议移除或合并的工具

无

## 其他备注

全量 dev_toolkit pytest 曾抓到 response_tools.py 命名触发 *_tools.py 组件契约，已改为 response_shaping.py。

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
    "calls": 628,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "sql",
    "calls": 503,
    "error": 25,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 485,
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
    "calls": 459,
    "error": 17,
    "avg_duration_seconds": 0.708
  },
  {
    "tool": "run_test",
    "calls": 417,
    "error": 2,
    "avg_duration_seconds": 3.941
  },
  {
    "tool": "code_impact",
    "calls": 403,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 394,
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
