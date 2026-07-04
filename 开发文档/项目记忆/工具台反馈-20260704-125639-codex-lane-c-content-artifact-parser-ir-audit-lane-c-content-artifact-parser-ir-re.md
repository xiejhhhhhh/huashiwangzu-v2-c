---
name: "工具台反馈-20260704-125639-codex-lane-c-content-artifact-parser-ir-audit-Lane C Content/Artifact/Parser IR re"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-lane-c-content-artifact-parser-ir-audit"
created: "2026-07-04T12:56:39.456877+00:00"
---

# MCP 使用反馈

## 任务

Lane C Content/Artifact/Parser IR readonly audit

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，CodeGraph 对 content 链路定位很快，工具台能力足够完成只读审计。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, routes, capabilities, db_schema, probe, call_capability, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

capabilities 全量输出过长且无法按 action 模糊过滤；code_node 不支持 offset 参数时需要回退 sed。finish_task 发现并发 dirty 但无法自动区分本会话写入与其它会话写入。

## 缺少的工具 / 能力

希望有 manifest/parser matrix 专用审计工具，能直接列模块 README、sandbox、public_actions、SUPPORTED_EXTS、返回 block type 与 Content IR schema 差异。

## 升级建议

给 capabilities 增加 module/action regex 过滤；给 code_node 增加 offset/limit 参数；给 worktree_guard 支持记录本会话前后快照并标注疑似外部并发变更。

## 建议移除或合并的工具

无

## 其他备注

任务要求只做审计；除项目规则要求的 memory/feedback 外未使用编辑工具修改源码。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.142
  },
  {
    "tool": "code_explore",
    "calls": 233,
    "error": 0,
    "avg_duration_seconds": 0.337
  },
  {
    "tool": "probe",
    "calls": 163,
    "error": 4,
    "avg_duration_seconds": 0.319
  },
  {
    "tool": "worktree_guard",
    "calls": 157,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.757
  },
  {
    "tool": "plan_task",
    "calls": 119,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "sql",
    "calls": 115,
    "error": 5,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "call_capability",
    "calls": 113,
    "error": 5,
    "avg_duration_seconds": 0.29
  },
  {
    "tool": "code_impact",
    "calls": 111,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "finish_task",
    "calls": 78,
    "error": 0,
    "avg_duration_seconds": 1.789
  }
]
```
