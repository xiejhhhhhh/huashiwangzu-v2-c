---
name: "工具台反馈-20260704-121235-codex-test-pollution-stability-r1-测试污染回归清零与门禁稳态收口：清零测试污染，并补强 release g"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-test-pollution-stability-r1"
created: "2026-07-04T12:12:35.508870+00:00"
---

# MCP 使用反馈

## 任务

测试污染回归清零与门禁稳态收口：清零测试污染，并补强 release gate 任一污染域非零即 BLOCKER。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，audit、release_gate、finish_task 能直接给出验收证据和边界检查结果。

## 本次用到的工具

brief, plan_task, code_explore, code_node, code_impact, test_data_pollution_audit, release_gate, probe, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

工作区并发脏改动很多，finish_task 需要手动整理较长 baseline_paths 才能表达本轮边界。

## 缺少的工具 / 能力

缺一个从当前 status 自动生成“排除本轮文件后的 baseline_paths”的小工具或 finish_task 参数。

## 升级建议

finish_task 可支持 current_changed_files 与 task_changed_files 自动求差，减少并发任务下的长 baseline 参数。

## 建议移除或合并的工具

无

## 其他备注

本次最终审计 active/recycled/knowledge/content/uploads/candidate 全 0，release_gate preflight 无 BLOCKER。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 319,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 192,
    "error": 0,
    "avg_duration_seconds": 0.336
  },
  {
    "tool": "probe",
    "calls": 143,
    "error": 4,
    "avg_duration_seconds": 0.325
  },
  {
    "tool": "worktree_guard",
    "calls": 131,
    "error": 0,
    "avg_duration_seconds": 0.029
  },
  {
    "tool": "call_capability",
    "calls": 104,
    "error": 5,
    "avg_duration_seconds": 0.291
  },
  {
    "tool": "brief",
    "calls": 103,
    "error": 0,
    "avg_duration_seconds": 0.752
  },
  {
    "tool": "plan_task",
    "calls": 101,
    "error": 0,
    "avg_duration_seconds": 0.005
  },
  {
    "tool": "code_impact",
    "calls": 100,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "sql",
    "calls": 99,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "finish_task",
    "calls": 66,
    "error": 0,
    "avg_duration_seconds": 1.536
  }
]
```
