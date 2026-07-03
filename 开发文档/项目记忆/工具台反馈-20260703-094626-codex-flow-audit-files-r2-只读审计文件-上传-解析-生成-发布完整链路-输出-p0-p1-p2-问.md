---
name: "工具台反馈-20260703-094626-codex-flow-audit-files-r2-只读审计文件/上传/解析/生成/发布完整链路，输出 P0/P1/P2 问"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-flow-audit-files-r2"
created: "2026-07-03T09:46:26.558192+00:00"
---

# MCP 使用反馈

## 任务

只读审计文件/上传/解析/生成/发布完整链路，输出 P0/P1/P2 问题队列和证据。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，code_node/code_explore 与只读 SQL 足够支撑链路审计。

## 本次用到的工具

brief, plan_task, worktree_guard, routes, capabilities, db_schema, db_reverse_audit, code_explore, code_node, code_impact, tail_log, sql, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

db_reverse_audit 的 table_filter 使用逗号关键词时返回 0 表，可能只支持单一 substring 或需要文档提示；capabilities 输出过长且中间截断，不适合精确审计全量能力。

## 缺少的工具 / 能力

希望增加专门的 runtime_artifact_audit/gitignore_audit 工具，自动列出 tracked runtime files、ignore gap、目录体积和最近提交来源；也希望有 file_access_audit 工具扫描 db.get(File)/storage_path/read_bytes/commonpath/check_file_access 组合。

## 升级建议

db_reverse_audit 可支持多关键词 OR；routes/capabilities 可支持 module/path/action 精确分页输出，减少截断。

## 建议移除或合并的工具

无

## 其他备注

本次遵守只读，不改代码、不 commit；memory_write/mcp_feedback 为项目规则要求的收工留痕。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 960,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 572,
    "error": 0,
    "avg_duration_seconds": 0.027
  },
  {
    "tool": "code_explore",
    "calls": 390,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "call_capability",
    "calls": 389,
    "error": 17,
    "avg_duration_seconds": 0.785
  },
  {
    "tool": "sql",
    "calls": 351,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 341,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "probe",
    "calls": 340,
    "error": 3,
    "avg_duration_seconds": 0.464
  },
  {
    "tool": "run_test",
    "calls": 327,
    "error": 2,
    "avg_duration_seconds": 3.281
  },
  {
    "tool": "worktree_guard",
    "calls": 322,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 263,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
