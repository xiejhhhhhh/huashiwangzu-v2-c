---
name: "工具台反馈-20260704-080925-codex-feedback-knowledge-product-r2-反馈中心可操作化与 Knowledge 产物质量二期：ActionIte"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-feedback-knowledge-product-r2"
created: "2026-07-04T08:09:25.589870+00:00"
---

# MCP 使用反馈

## 任务

反馈中心可操作化与 Knowledge 产物质量二期：ActionItem 聚合/跳转/忽略，Knowledge 导出契约校验与去重，source unavailable 用户处理路径与状态文案。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，finish_task 能一次性汇总边界、lint、pytest 与风险模板，适合收口。

## 本次用到的工具

brief, plan_task, worktree_guard, codegraph/code_explore, lint, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard/finish_task 对既有未跟踪项目记忆缺少开工基线时会全部标为新变更，需要人工解释基线；多代理结果与主会话验证之间仍需人工整理。

## 缺少的工具 / 能力

希望有一个可直接读取本轮开工基线并自动带入 finish_task 的工具，减少对既有 dirty 文档的重复说明。

## 升级建议

finish_task 可以支持把已跑过的活栈 probe/capability 原始摘要结构化粘贴后自动生成验收矩阵；也可增加浏览器截图未跑时的明确风险分类。

## 建议移除或合并的工具

无。

## 其他备注

本次任务同时跨 frontend 框架反馈中心与 modules/knowledge，需要使用 allowed_prefixes 而不是 module_key；边界守卫输出清晰。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1532,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "probe",
    "calls": 791,
    "error": 8,
    "avg_duration_seconds": 0.424
  },
  {
    "tool": "code_explore",
    "calls": 748,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "lint",
    "calls": 684,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "sql",
    "calls": 674,
    "error": 42,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "call_capability",
    "calls": 613,
    "error": 18,
    "avg_duration_seconds": 0.606
  },
  {
    "tool": "worktree_guard",
    "calls": 571,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 508,
    "error": 3,
    "avg_duration_seconds": 4.412
  },
  {
    "tool": "code_impact",
    "calls": 497,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 473,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
