---
name: "工具台反馈-20260703-072628-codex-conductor-sweep-20260703-r2-主会话验收并提交 scheduler/web-tools/github-"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:26:28.153472+00:00"
---

# MCP 使用反馈

## 任务

主会话验收并提交 scheduler/web-tools/github-search r2 扫雷修复

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，probe/call_capability 对活系统验收很有用。

## 本次用到的工具

capabilities, probe, call_capability, finish_task, memory_write, mcp_feedback, worktree_guard

## 卡点 / 不顺手的地方

finish_task 将多个 sandbox/test_module.py 合并进同一次 pytest 时会触发 import file mismatch；call_capability 曾瞬时返回 All connection attempts failed，但健康检查重试正常。

## 缺少的工具 / 能力

希望 finish_task 支持 sandbox basename 冲突自动拆分运行，call_capability 连接失败时返回后端端口/重试建议。

## 升级建议

为 finish_task 增加 pytest --import-mode=importlib 或逐目标隔离模式；为工具台 HTTP client 增加一次短退避重试与错误分类。

## 建议移除或合并的工具

无

## 其他备注

GitHub 搜索依赖外网和 gh CLI 登录状态，主会话已用 search/search_code 正常路径验收通过。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 721,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 501,
    "error": 0,
    "avg_duration_seconds": 0.023
  },
  {
    "tool": "code_explore",
    "calls": 325,
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
    "tool": "call_capability",
    "calls": 286,
    "error": 16,
    "avg_duration_seconds": 0.694
  },
  {
    "tool": "run_test",
    "calls": 281,
    "error": 2,
    "avg_duration_seconds": 3.649
  },
  {
    "tool": "worktree_guard",
    "calls": 271,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 254,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 225,
    "error": 2,
    "avg_duration_seconds": 0.515
  },
  {
    "tool": "db_schema",
    "calls": 220,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
