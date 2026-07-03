---
name: "工具台反馈-20260703-111555-codex-conductor-r4-形成 R4 底层收口落地方案，把进度口径从 dirty 文件改成底层能力"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-conductor-r4"
created: "2026-07-03T11:15:55.696015+00:00"
---

# MCP 使用反馈

## 任务

形成 R4 底层收口落地方案，把进度口径从 dirty 文件改成底层能力域验收。

## 顺畅度

- 评分：4/5
- 体感：memory_write 适合沉淀战役级方案，能避免子代理结果碎片化。

## 本次用到的工具

brief, plan_task, worktree_guard, probe, finish_task, memory_write

## 卡点 / 不顺手的地方

多代理共享工作区时 finish_task 的 dirty 统计会混入其他域，需要主会话按提交切片过滤。

## 缺少的工具 / 能力

希望工具台提供按能力域聚合 dirty/测试/探针结果的 dashboard。

## 升级建议

增加 bottom_layer_status 工具，自动汇总 health、task debt、contract drift、sandbox、release gate。

## 建议移除或合并的工具

无

## 其他备注

用户指出需要大局观后，主会话已切换为底层能力域总控。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1116,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 614,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "code_explore",
    "calls": 456,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "probe",
    "calls": 456,
    "error": 6,
    "avg_duration_seconds": 0.45
  },
  {
    "tool": "sql",
    "calls": 447,
    "error": 23,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 444,
    "error": 17,
    "avg_duration_seconds": 0.722
  },
  {
    "tool": "run_test",
    "calls": 398,
    "error": 2,
    "avg_duration_seconds": 3.283
  },
  {
    "tool": "code_impact",
    "calls": 393,
    "error": 0,
    "avg_duration_seconds": 0.135
  },
  {
    "tool": "worktree_guard",
    "calls": 372,
    "error": 0,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "db_schema",
    "calls": 318,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
