---
name: "工具台反馈-20260703-080040-codex-image-vision-sweep-20260703-r2-审计并修复 modules/image-vision 图片分析链路：本地"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-image-vision-sweep-20260703-r2"
created: "2026-07-03T08:00:40.423966+00:00"
---

# MCP 使用反馈

## 任务

审计并修复 modules/image-vision 图片分析链路：本地确定性分析优先、必要时再 VLM，修复坏参数 500，补 sandbox 与前端面板。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅；brief/plan_task/codegraph/探针/finish_task 串起来能覆盖证据、改动和验收。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, lint, run_test, probe, call_capability, tail_log, finish_task, memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 在多 agent 脏工作区下只能给全局红灯，无法标记哪些文件是本 agent 本轮新增/修改，最终需要人工结合 git diff --name-only -- modules/image-vision 解释。

## 缺少的工具 / 能力

希望有按 agent/路径白名单的 finish_task 边界模式，允许把本人项目记忆文件列入 allowed_prefixes，同时显示 outside dirty 为 pre-existing warning 而非 task failure。

## 升级建议

call_capability 的长 JSON 输出可以增加 JSONPath 摘要模式，例如只看 success/error/data.analysis_strategy，减少日志噪音。

## 建议移除或合并的工具

无

## 其他备注

本次未强制 semantic VLM 真调用以避免外部模型成本；用 local-only 活系统调用验证 external_vlm_calls=0，并验证坏参数统一错误。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 830,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 541,
    "error": 0,
    "avg_duration_seconds": 0.026
  },
  {
    "tool": "code_explore",
    "calls": 347,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 342,
    "error": 17,
    "avg_duration_seconds": 0.688
  },
  {
    "tool": "probe",
    "calls": 308,
    "error": 3,
    "avg_duration_seconds": 0.479
  },
  {
    "tool": "sql",
    "calls": 307,
    "error": 14,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "run_test",
    "calls": 303,
    "error": 2,
    "avg_duration_seconds": 3.477
  },
  {
    "tool": "worktree_guard",
    "calls": 296,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 293,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "db_schema",
    "calls": 236,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
