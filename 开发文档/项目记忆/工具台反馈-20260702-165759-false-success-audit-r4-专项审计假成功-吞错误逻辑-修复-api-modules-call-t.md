---
name: "工具台反馈-20260702-165759-false-success-audit-r4-专项审计假成功/吞错误逻辑，修复 /api/modules/call、t"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "false-success-audit-r4"
created: "2026-07-02T16:57:59.577960+00:00"
---

# MCP 使用反馈

## 任务

专项审计假成功/吞错误逻辑，修复 /api/modules/call、terminal-tools、web-tools 的 failure 外层假绿，并修正 access-control 测试桩/唯一上传名。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan/worktree/codegraph 能快速建立边界，probe 很快确认了假绿是活系统真实问题。

## 本次用到的工具

brief, plan_task, worktree_guard, code_explore, tail_log, probe, finish_task, memory_write, mcp_feedback

## 卡点 / 不顺手的地方

finish_task/run_test 合跑两个不同目录下同名 sandbox/test_module.py 时会触发 pytest import file mismatch，分开跑才是正确姿势；finish_task 因此显示 success=false，但实际人工分跑已通过。

## 缺少的工具 / 能力

希望 run_test/finish_task 支持 sandbox 矩阵式隔离执行同名 test_module.py，或自动拆分不同模块 sandbox。

## 升级建议

可以新增 false_success_scan 工具：AST 扫描 ApiResponse(data=result) + result.success false / data.error 模式，并输出候选端点、活系统 probe 样例和建议替换点。

## 建议移除或合并的工具

无

## 其他备注

tail_log 本轮无输出；code_explore 对假成功关键词命中较泛，最终靠 rg/AST/probe 交叉确认。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 389,
    "error": 0,
    "avg_duration_seconds": 0.145
  },
  {
    "tool": "lint",
    "calls": 269,
    "error": 0,
    "avg_duration_seconds": 0.016
  },
  {
    "tool": "sql",
    "calls": 198,
    "error": 8,
    "avg_duration_seconds": 0.031
  },
  {
    "tool": "code_explore",
    "calls": 192,
    "error": 0,
    "avg_duration_seconds": 0.312
  },
  {
    "tool": "worktree_guard",
    "calls": 126,
    "error": 0,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "code_impact",
    "calls": 123,
    "error": 0,
    "avg_duration_seconds": 0.138
  },
  {
    "tool": "db_schema",
    "calls": 118,
    "error": 0,
    "avg_duration_seconds": 0.033
  },
  {
    "tool": "run_test",
    "calls": 116,
    "error": 0,
    "avg_duration_seconds": 2.258
  },
  {
    "tool": "probe",
    "calls": 102,
    "error": 0,
    "avg_duration_seconds": 0.527
  },
  {
    "tool": "plan_task",
    "calls": 87,
    "error": 0,
    "avg_duration_seconds": 0.007
  }
]
```
