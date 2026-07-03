---
name: "工具台反馈-20260703-080252-codex-email-parser-sweep-20260703-r2-modules/email-parser r2 sweep: harde"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-email-parser-sweep-20260703-r2"
created: "2026-07-03T08:02:52.894127+00:00"
---

# MCP 使用反馈

## 任务

modules/email-parser r2 sweep: hardened parser errors/resources/HTML/plaintext/attachments, rewired sandbox to production parser, added README and validation evidence.

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 和工具台足够定位权限链路与模块影响面。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

finish_task/worktree_guard 在多 agent 脏工作区里会把其他 agent 的改动和允许的项目记忆一起算成模块边界失败，需要人工解释基线。活栈 capability 命中旧注册函数时缺少一键判断是否需要模块热重载的提示。

## 缺少的工具 / 能力

希望有按 agent/路径白名单做边界验收的 finish_task 参数，允许 modules/{key}/ 加本 agent 项目记忆，同时忽略开工时 baseline dirty。

## 升级建议

给 call_capability 增加返回当前模块代码版本/进程启动时间或注册 handler 来源文件 mtime，便于判断 stale handler。

## 建议移除或合并的工具

无

## 其他备注

未重启常驻后端；health 可用，bad file_id capability 仍 500，但本地导入新 router 已验证会抛 ValidationError。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 854,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 545,
    "error": 0,
    "avg_duration_seconds": 0.026
  },
  {
    "tool": "code_explore",
    "calls": 350,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 345,
    "error": 17,
    "avg_duration_seconds": 0.684
  },
  {
    "tool": "probe",
    "calls": 312,
    "error": 3,
    "avg_duration_seconds": 0.476
  },
  {
    "tool": "sql",
    "calls": 308,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 306,
    "error": 2,
    "avg_duration_seconds": 3.45
  },
  {
    "tool": "code_impact",
    "calls": 303,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "worktree_guard",
    "calls": 299,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 239,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
