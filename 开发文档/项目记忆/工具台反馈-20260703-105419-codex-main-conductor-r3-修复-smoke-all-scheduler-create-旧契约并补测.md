---
name: "工具台反馈-20260703-105419-codex-main-conductor-r3-修复 smoke_all scheduler create 旧契约并补测"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-main-conductor-r3"
created: "2026-07-03T10:54:19.905482+00:00"
---

# MCP 使用反馈

## 任务

修复 smoke_all scheduler create 旧契约并补测试数据清理

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，smoke_all 很快暴露旧契约；capabilities/routes 帮助确认真实参数。

## 本次用到的工具

codegraph explore, capabilities, routes, smoke_all, tail_log, ruff, shell DB cleanup

## 卡点 / 不顺手的地方

smoke_all 内部只显示最终红点，定位到具体旧 payload 还需要 codegraph/rg；工具台可考虑输出失败场景的请求 payload 摘要。

## 缺少的工具 / 能力

建议增加 smoke scenario cleanup audit，自动列出本轮创建但未删除的 file/task/kb 记录。

## 升级建议

smoke_all 可把每个场景的 cleanup_count 结构化返回，避免只靠日志阅读。

## 建议移除或合并的工具

无

## 其他备注

本轮修复没有改业务模块，只修验收脚本。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1069,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 600,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "code_explore",
    "calls": 436,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "sql",
    "calls": 425,
    "error": 22,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 415,
    "error": 17,
    "avg_duration_seconds": 0.754
  },
  {
    "tool": "probe",
    "calls": 414,
    "error": 3,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "run_test",
    "calls": 376,
    "error": 2,
    "avg_duration_seconds": 3.153
  },
  {
    "tool": "code_impact",
    "calls": 372,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 356,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 304,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
