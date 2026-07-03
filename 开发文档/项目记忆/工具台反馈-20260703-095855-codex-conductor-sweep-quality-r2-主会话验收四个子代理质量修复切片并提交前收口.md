---
name: "工具台反馈-20260703-095855-codex-conductor-sweep-quality-r2-主会话验收四个子代理质量修复切片并提交前收口"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-sweep-quality-r2"
created: "2026-07-03T09:58:55.930312+00:00"
---

# MCP 使用反馈

## 任务

主会话验收四个子代理质量修复切片并提交前收口

## 顺畅度

- 评分：4/5
- 体感：工具台整体顺畅，lint/run_test/probe 组合能快速抓到子代理遗漏。

## 本次用到的工具

brief, plan_task, worktree_guard, code_impact, lint, run_test, probe, call_capability, tail_log, opencode_sdk_job_status, memory_write, finish_task

## 卡点 / 不顺手的地方

finish_task 对多目标 pytest 合并时可能不如逐个 run_test 清晰；opencode SDK job 本轮 stalled 且 messages 为空，诊断价值有限。

## 缺少的工具 / 能力

希望有一个按 git pathspec 分组生成可提交切片摘要的工具，方便主会话验收多代理并行改动。

## 升级建议

opencode_sdk_job_status 在 stalled 时可直接暴露最近 stdout/stderr 或失败原因摘要；finish_task 可支持传入已完成验证结果，避免重复跑较慢测试。

## 建议移除或合并的工具

无

## 其他备注

主会话验收发现 agent 切片重复 normalizer 逻辑和名称遮蔽 runtime bug，说明验收环节必须保留。

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
    "calls": 578,
    "error": 0,
    "avg_duration_seconds": 0.028
  },
  {
    "tool": "call_capability",
    "calls": 391,
    "error": 17,
    "avg_duration_seconds": 0.782
  },
  {
    "tool": "code_explore",
    "calls": 391,
    "error": 0,
    "avg_duration_seconds": 0.329
  },
  {
    "tool": "sql",
    "calls": 351,
    "error": 15,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "probe",
    "calls": 349,
    "error": 3,
    "avg_duration_seconds": 0.467
  },
  {
    "tool": "code_impact",
    "calls": 346,
    "error": 0,
    "avg_duration_seconds": 0.136
  },
  {
    "tool": "run_test",
    "calls": 339,
    "error": 2,
    "avg_duration_seconds": 3.19
  },
  {
    "tool": "worktree_guard",
    "calls": 324,
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
