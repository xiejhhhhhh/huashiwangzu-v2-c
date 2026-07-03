---
name: "工具台反馈-20260703-074343-codex-conductor-sweep-20260703-r2-主会话验收并提交 docs-open r2 token 与假成功修复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:43:43.878373+00:00"
---

# MCP 使用反馈

## 任务

主会话验收并提交 docs-open r2 token 与假成功修复

## 顺畅度

- 评分：4/5
- 体感：routes 查准真实 /api/docs 前缀后，probe 和 call_capability 能覆盖 token、安全边界与能力异常映射。

## 本次用到的工具

routes,capabilities,probe,call_capability,memory_write,mcp_feedback,ruff,pytest,compileall

## 卡点 / 不顺手的地方

模块 key 是 docs-open 但 HTTP route_prefix 是 /api/docs，直觉用 /api/docs-open 会误测 404。

## 缺少的工具 / 能力

希望 routes(module=docs-open) 能按 manifest/router 反查真实前缀，不只文本过滤。

## 升级建议

为 capabilities 输出附带 route_prefix，减少模块 key 与 HTTP 前缀不一致造成的误判。

## 建议移除或合并的工具

无

## 其他备注

未创建业务测试数据。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 762,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 523,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 332,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 317,
    "error": 17,
    "avg_duration_seconds": 0.721
  },
  {
    "tool": "sql",
    "calls": 303,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 294,
    "error": 2,
    "avg_duration_seconds": 3.564
  },
  {
    "tool": "worktree_guard",
    "calls": 283,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 271,
    "error": 2,
    "avg_duration_seconds": 0.49
  },
  {
    "tool": "code_impact",
    "calls": 270,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 228,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
