---
name: "工具台反馈-20260703-074322-codex-docx-parser-sweep-20260703-r2-modules/docx-parser r2 sweep: parser"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-docx-parser-sweep-20260703-r2"
created: "2026-07-03T07:43:22.701065+00:00"
---

# MCP 使用反馈

## 任务

modules/docx-parser r2 sweep: parser hardening and sandbox real tests

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph/工具台很快定位了安全通路和模块影响面。

## 本次用到的工具

brief, plan_task, worktree_guard, capabilities, routes, code_explore, code_node, code_impact, memory_search, lint, run_test, probe, call_capability, sql, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

run_test 默认 PYTHONPATH 为 repo root，而文件解析模块 sandbox 文档要求 PYTHONPATH=backend；这次靠修 sandbox 自带 sys.path 解决。worktree_guard 在并发多 agent 脏工作区下会持续 success:false，需要人工区分本任务改动和既有改动。

## 缺少的工具 / 能力

希望 worktree_guard/finish_task 支持 baseline 快照或只评估本 agent 自上次 memory_write 之后新增/修改的路径。

## 升级建议

run_test 可支持 per-module env 参数，或读取模块 README/sandbox 配置中的 PYTHONPATH 建议。

## 建议移除或合并的工具

无

## 其他备注

call_capability 对 file_id=0 返回 success:false 但 HTTP 500，体现能力入口对参数校验异常仍偏内部错误；本次未越界改框架。

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
    "tool": "code_impact",
    "calls": 270,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 270,
    "error": 2,
    "avg_duration_seconds": 0.491
  },
  {
    "tool": "db_schema",
    "calls": 228,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
