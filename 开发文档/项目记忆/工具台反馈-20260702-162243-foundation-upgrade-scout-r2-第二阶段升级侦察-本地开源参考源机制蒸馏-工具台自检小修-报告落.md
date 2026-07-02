---
name: "工具台反馈-20260702-162243-foundation-upgrade-scout-r2-第二阶段升级侦察：本地开源参考源机制蒸馏 + 工具台自检小修 + 报告落"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "foundation-upgrade-scout-r2"
created: "2026-07-02T16:22:43.248556+00:00"
---

# MCP 使用反馈

## 任务

第二阶段升级侦察：本地开源参考源机制蒸馏 + 工具台自检小修 + 报告落盘

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree_guard/codegraph/工具台统计/记忆工具能支撑侦察闭环；真实 MCP stdio 调用帮助发现了单测未覆盖的问题。

## 本次用到的工具

brief, plan_task, worktree_guard, mcp_feedback_summary, tool_usage_stats, mcp_self_check, dev_toolkit_architecture_audit, module_sandbox_matrix, routes, capabilities, codegraph CLI, memory_write, finish_task, mcp_feedback

## 卡点 / 不顺手的地方

mcp_self_check 和 dev_toolkit_architecture_audit 起初在真实 MCP stdio 路径报 No module named dev_toolkit，已小修；python3.14 系统环境没有 ruff，需要改用 backend/.venv/bin/python -m ruff。工作区中途出现大量其他 agent 并发改动，finish_task 的 dirty 摘要噪声较高。

## 缺少的工具 / 能力

建议增加 reference_sources_scan 工具：列出本地参考源项目、README、重点源码文件与最近下载时间；建议增加 stdio_tool_smoke，直接通过 MCP 协议调用指定工具，避免只测 Python import。

## 升级建议

P0：工具台高频工具 schema 支持 object 参数并兼容旧 string；P0：memory_write slug 防覆盖和文件锁；P1：mcp_self_check 纳入 release_gate；P1：工具调用统计支持 server 层 agent attribution，不依赖每个工具参数自带 agent。

## 建议移除或合并的工具

暂无移除建议；但 server.py 仍偏大，应继续把核心实现迁出到组件。

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 328,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 246,
    "error": 0,
    "avg_duration_seconds": 0.017
  },
  {
    "tool": "sql",
    "calls": 170,
    "error": 7,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 167,
    "error": 0,
    "avg_duration_seconds": 0.309
  },
  {
    "tool": "code_impact",
    "calls": 104,
    "error": 0,
    "avg_duration_seconds": 0.139
  },
  {
    "tool": "worktree_guard",
    "calls": 104,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "db_schema",
    "calls": 97,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 94,
    "error": 0,
    "avg_duration_seconds": 2.601
  },
  {
    "tool": "probe",
    "calls": 80,
    "error": 0,
    "avg_duration_seconds": 0.587
  },
  {
    "tool": "plan_task",
    "calls": 72,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
