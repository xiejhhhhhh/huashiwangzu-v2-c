---
name: "工具台反馈-20260704-143624-codex-parser-ir-conductor-Parser Content IR 全解析器权威归一总收口：协调 5 子"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-parser-ir-conductor"
created: "2026-07-04T14:36:24.383959+00:00"
---

# MCP 使用反馈

## 任务

Parser Content IR 全解析器权威归一总收口：协调 5 子代理、验证 11 parser/vision/media 模块、补 normalizer adapter、跑 lint/架构测试/sandbox matrix、生成交付。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，codegraph/工具台/子代理组合很适合这种多模块矩阵任务。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, lint, run_test, module_sandbox_matrix, memory_write, mcp_feedback, mailbox_create_delivery_bundle

## 卡点 / 不顺手的地方

多代理并行时工作区出现任务外 dirty 且部分已 staged，finish/commit 阶段需要额外 scoped commit 和边界说明；pytest 多个同名 sandbox/test_module.py 合跑会 import mismatch。

## 缺少的工具 / 能力

缺一个可以按 pathspec 安全生成 scoped commit/交付 diff 的工具，并能显式忽略并行任务外 staged 文件。

## 升级建议

module_sandbox_matrix 可提供只跑指定模块且输出简短 summary 的 MCP 同步接口；worktree_guard 可支持记录开工 baseline 后自动区分“本任务新增”和“外部并行新增”。

## 建议移除或合并的工具

无

## 其他备注

无

## 当前工具热度快照

```json
[
  {
    "tool": "run_test",
    "calls": 35,
    "error": 0,
    "avg_duration_seconds": 2.674
  },
  {
    "tool": "lint",
    "calls": 16,
    "error": 0,
    "avg_duration_seconds": 0.087
  },
  {
    "tool": "probe",
    "calls": 16,
    "error": 3,
    "avg_duration_seconds": 0.229
  },
  {
    "tool": "code_node",
    "calls": 15,
    "error": 0,
    "avg_duration_seconds": 0.147
  },
  {
    "tool": "code_impact",
    "calls": 11,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "worktree_guard",
    "calls": 10,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "finish_task",
    "calls": 9,
    "error": 0,
    "avg_duration_seconds": 0.56
  },
  {
    "tool": "capabilities",
    "calls": 6,
    "error": 0,
    "avg_duration_seconds": 0.001
  },
  {
    "tool": "tail_log",
    "calls": 4,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "tool_job_submit",
    "calls": 4,
    "error": 0,
    "avg_duration_seconds": 0.011
  }
]
```
