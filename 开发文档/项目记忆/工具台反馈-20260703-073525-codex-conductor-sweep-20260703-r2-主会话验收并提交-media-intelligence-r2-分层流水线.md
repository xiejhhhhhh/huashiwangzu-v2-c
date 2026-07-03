---
name: "工具台反馈-20260703-073525-codex-conductor-sweep-20260703-r2-主会话验收并提交 media-intelligence r2 分层流水线"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:35:25.869370+00:00"
---

# MCP 使用反馈

## 任务

主会话验收并提交 media-intelligence r2 分层流水线骨架

## 顺畅度

- 评分：4/5
- 体感：routes/capabilities/call_capability 组合很好地抓到了新增模块接入后 capability 与 HTTP 参数语义不一致的问题。

## 本次用到的工具

capabilities,routes,probe,call_capability,code_node,tail_log,memory_write,mcp_feedback

## 卡点 / 不顺手的地方

sandbox 导入 router 时会触发后端 Settings 的 JWT_SECRET 校验，新增模块测试需要显式设置测试环境变量。

## 缺少的工具 / 能力

希望工具台能提供 capability fuzz：自动对 manifest 参数生成 0/空/越界值，检查是否返回统一 4xx 而不是 500。

## 升级建议

为 call_capability 增加批量坏参扫描和统一响应断言；为新增模块验收增加 routes + capabilities 差异检查。

## 建议移除或合并的工具

无

## 其他备注

本轮没有引入重依赖，只建立本地算法/小模型/VLM 分层契约。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 740,
    "error": 0,
    "avg_duration_seconds": 0.146
  },
  {
    "tool": "lint",
    "calls": 513,
    "error": 0,
    "avg_duration_seconds": 0.025
  },
  {
    "tool": "code_explore",
    "calls": 327,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 301,
    "error": 13,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 300,
    "error": 17,
    "avg_duration_seconds": 0.747
  },
  {
    "tool": "run_test",
    "calls": 288,
    "error": 2,
    "avg_duration_seconds": 3.628
  },
  {
    "tool": "worktree_guard",
    "calls": 277,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_impact",
    "calls": 259,
    "error": 0,
    "avg_duration_seconds": 0.137
  },
  {
    "tool": "probe",
    "calls": 247,
    "error": 2,
    "avg_duration_seconds": 0.514
  },
  {
    "tool": "db_schema",
    "calls": 225,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
