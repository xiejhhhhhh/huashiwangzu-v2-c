---
name: "工具台反馈-20260705-081027-codex-image-gen Provider 链路产品化收口并提交 93aded"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex"
created: "2026-07-05T08:10:27.798343+00:00"
---

# MCP 使用反馈

## 任务

image-gen Provider 链路产品化收口并提交 93aded13

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph/能力/路由/表结构工具能快速定位边界和契约。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard 的开工基线在并行任务持续写入时需要手工补 baseline；活系统重启脚本未能识别多 worker 子进程，需要手工 kill uvicorn parent 后由 watchdog 拉起。

## 缺少的工具 / 能力

缺一个安全的模块自有表写入/测试数据清理工具，当前只能用 psql 精确清理 imagegen_records。

## 升级建议

start_backend --restart 可兼容 uvicorn --workers 的 parent/child 识别；worktree_guard 可支持追加 baseline 或按 commit staged 文件生成边界报告。

## 建议移除或合并的工具

无

## 其他备注

本次未调用真实外部 image provider，使用 placeholder 安全路径验活系统。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.143
  },
  {
    "tool": "probe",
    "calls": 74,
    "error": 3,
    "avg_duration_seconds": 0.268
  },
  {
    "tool": "run_test",
    "calls": 67,
    "error": 0,
    "avg_duration_seconds": 3.117
  },
  {
    "tool": "code_impact",
    "calls": 46,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "sql",
    "calls": 37,
    "error": 6,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "worktree_guard",
    "calls": 37,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "lint",
    "calls": 32,
    "error": 0,
    "avg_duration_seconds": 0.086
  },
  {
    "tool": "call_capability",
    "calls": 28,
    "error": 0,
    "avg_duration_seconds": 0.524
  },
  {
    "tool": "code_explore",
    "calls": 24,
    "error": 1,
    "avg_duration_seconds": 0.347
  },
  {
    "tool": "capabilities",
    "calls": 22,
    "error": 0,
    "avg_duration_seconds": 0.001
  }
]
```
