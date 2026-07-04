---
name: "工具台反馈-20260704-115306-codex-agent-evidence-clickback-r1-Agent 证据引用点击回源闭环：后端 summary 保留引用 met"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-evidence-clickback-r1"
created: "2026-07-04T11:53:06.225260+00:00"
---

# MCP 使用反馈

## 任务

Agent 证据引用点击回源闭环：后端 summary 保留引用 metadata，前端工作流与工具结果统一展示证据卡片，file_id 带鉴权打开。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_explore、call_capability、finish_task 对收口很有帮助。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, capabilities, routes, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task 的 lint_paths 参数对目录路径报“文件不存在”，与我手动执行 ruff check 目录的常规用法不一致；重跑时去掉 lint_paths 才成功。

## 缺少的工具 / 能力

希望有一个组件级前端 smoke/DOM 快照工具，可以用 mock props 挂载 Vue 组件验证“含引用 workflow 可见卡片”，不必污染活栈数据库。

## 升级建议

finish_task 可接受目录 lint 路径并自动转为 ruff check <dir>，或在 schema/错误信息里明确只收文件列表。

## 建议移除或合并的工具

无

## 其他备注

本轮有大量并行 dirty 文件，baseline 机制有效避免误判；但 memory 目录并行未跟踪文件很多，收工输出较长。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 297,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 181,
    "error": 0,
    "avg_duration_seconds": 0.337
  },
  {
    "tool": "worktree_guard",
    "calls": 122,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "probe",
    "calls": 119,
    "error": 3,
    "avg_duration_seconds": 0.34
  },
  {
    "tool": "call_capability",
    "calls": 100,
    "error": 5,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "sql",
    "calls": 99,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 95,
    "error": 0,
    "avg_duration_seconds": 0.749
  },
  {
    "tool": "plan_task",
    "calls": 93,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 92,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "finish_task",
    "calls": 60,
    "error": 0,
    "avg_duration_seconds": 1.445
  }
]
```
