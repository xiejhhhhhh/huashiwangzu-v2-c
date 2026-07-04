---
name: "工具台反馈-20260704-131637-codex-full-productization-r1-全链路产品化落地总攻：补齐 Knowledge/Agent/Parser"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-full-productization-r1"
created: "2026-07-04T13:16:37.753278+00:00"
---

# MCP 使用反馈

## 任务

全链路产品化落地总攻：补齐 Knowledge/Agent/Parser IR/Desktop/ReleaseGate 主链路，并修复 full gate 测试数据污染残留。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/worktree_guard/release_gate/test_data_pollution_cleanup 形成了完整收口闭环。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, code_node, code_impact, db_schema, call_capability, probe, tail_log, tool_job_submit, smoke_all, release_gate, test_data_pollution_audit, test_data_pollution_cleanup, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

tool_job_submit 的 lint 参数只能传单个 path，run_test 参数名为 target；返回错误后需要改用直接 ruff 或重新提交，建议 schema/error message 里展示示例。后台 job 日志有缓冲，长任务中间可观测性偏弱。

## 缺少的工具 / 能力

缺少 job status 查询工具；只能 tail log 或 ps 查进度。建议提供 tool_job_status(job_id) 和最近 RELEASE_GATE_JSON 读取工具。

## 升级建议

release_gate full 中 smoke/sandbox 子进程建议强制 unbuffered 输出；lint 工具支持多文件路径；release_gate 可以在 smoke 结束后直接记录 Z3 清理摘要到 gate context。

## 建议移除或合并的工具

无。

## 其他备注

test_data_pollution_cleanup 非常有用，本轮将其接入 smoke.py 后 full gate 从 BLOCKER 回到 PASS_WITH_DEBT。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 414,
    "error": 0,
    "avg_duration_seconds": 0.148
  },
  {
    "tool": "code_explore",
    "calls": 253,
    "error": 0,
    "avg_duration_seconds": 0.342
  },
  {
    "tool": "probe",
    "calls": 167,
    "error": 4,
    "avg_duration_seconds": 0.325
  },
  {
    "tool": "worktree_guard",
    "calls": 166,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "brief",
    "calls": 126,
    "error": 0,
    "avg_duration_seconds": 0.759
  },
  {
    "tool": "plan_task",
    "calls": 125,
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
    "calls": 114,
    "error": 5,
    "avg_duration_seconds": 0.29
  },
  {
    "tool": "code_impact",
    "calls": 113,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "db_schema",
    "calls": 85,
    "error": 0,
    "avg_duration_seconds": 0.032
  }
]
```
