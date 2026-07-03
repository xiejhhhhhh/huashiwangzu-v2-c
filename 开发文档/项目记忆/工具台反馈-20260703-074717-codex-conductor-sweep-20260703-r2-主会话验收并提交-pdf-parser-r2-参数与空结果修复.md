---
name: "工具台反馈-20260703-074717-codex-conductor-sweep-20260703-r2-主会话验收并提交 pdf-parser r2 参数与空结果修复"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:47:17.520086+00:00"
---

# MCP 使用反馈

## 任务

主会话验收并提交 pdf-parser r2 参数与空结果修复

## 顺畅度

- 评分：3/5
- 体感：工具台能力调用本身顺畅，但重启脚本没有真正换掉多 worker uvicorn 父进程，导致一度误判新代码失败。

## 本次用到的工具

routes,capabilities,probe,call_capability,memory_write,mcp_feedback,ruff,pytest,tail_log

## 卡点 / 不顺手的地方

scripts/start_backend.sh --restart 在多 worker 场景只看一个 listen PID，可能拿到 worker 而不是 uvicorn 父进程，导致旧代码继续在线。

## 缺少的工具 / 能力

希望有 backend_restart_verified 工具，重启后能校验 PID/启动时间/代码加载时间。

## 升级建议

项目工具台可增加 active_backend_process_tree 和 verified_restart；start_backend.sh 应枚举全部 listen PID 并杀父 uvicorn。

## 建议移除或合并的工具

无

## 其他备注

pdf-parser 500 已通过真正重启后确认修复。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 780,
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
    "calls": 336,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 321,
    "error": 17,
    "avg_duration_seconds": 0.716
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
    "calls": 286,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 274,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 274,
    "error": 2,
    "avg_duration_seconds": 0.488
  },
  {
    "tool": "db_schema",
    "calls": 230,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
