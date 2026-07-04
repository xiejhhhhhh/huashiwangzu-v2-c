---
name: "工具台反馈-20260703-203800-codex-agent-workflow-runtime-link-执行 Agent workflow 中枢接入真实运行链路二阶段补强：审批"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-agent-workflow-runtime-link"
created: "2026-07-03T20:38:00.095775+00:00"
---

# MCP 使用反馈

## 任务

执行 Agent workflow 中枢接入真实运行链路二阶段补强：审批等待语义、慢工具队列归属、模型错误失败入账、skill_use 子 Agent 结果归集和测试/活系统验证。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/codegraph/run_test/capability 工具链能快速把真实链路和验收闭上。

## 本次用到的工具

brief
plan_task
worktree_guard
code_explore
code_node
code_impact
routes
capabilities
db_schema
lint
run_test
capability_contract_diff
call_capability
sql
finish_task
memory_write

## 卡点 / 不顺手的地方

worktree_guard/finish_task 对开工前大量未跟踪外部脏改动的 baseline 传递不够省心；需要手动摘路径且仍容易把并行任务新增文件标成边界失败。

## 缺少的工具 / 能力

希望有一个 begin_task 返回 baseline_token，finish_task 直接引用 token 做边界差分；以及一个受控 cleanup_probe_data 工具可按 marker 清理模块测试数据。

## 升级建议

finish_task 可支持 baseline_status_json 自动从 earlier worktree_guard tool result id 读取，减少长 JSON/路径复制。

## 建议移除或合并的工具

无

## 其他备注

活系统探针创建 run 6/7/8 后已手工清理，并用 SQL 确认剩余 0。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 1461,
    "error": 0,
    "avg_duration_seconds": 0.144
  },
  {
    "tool": "probe",
    "calls": 685,
    "error": 8,
    "avg_duration_seconds": 0.441
  },
  {
    "tool": "code_explore",
    "calls": 684,
    "error": 0,
    "avg_duration_seconds": 0.328
  },
  {
    "tool": "lint",
    "calls": 680,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "sql",
    "calls": 589,
    "error": 35,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "call_capability",
    "calls": 560,
    "error": 18,
    "avg_duration_seconds": 0.638
  },
  {
    "tool": "worktree_guard",
    "calls": 536,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "run_test",
    "calls": 500,
    "error": 3,
    "avg_duration_seconds": 4.417
  },
  {
    "tool": "code_impact",
    "calls": 491,
    "error": 0,
    "avg_duration_seconds": 0.134
  },
  {
    "tool": "db_schema",
    "calls": 441,
    "error": 0,
    "avg_duration_seconds": 0.033
  }
]
```
