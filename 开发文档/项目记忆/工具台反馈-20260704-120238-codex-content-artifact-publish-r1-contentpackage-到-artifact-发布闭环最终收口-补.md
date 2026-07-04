---
name: "工具台反馈-20260704-120238-codex-content-artifact-publish-r1-ContentPackage 到 Artifact 发布闭环最终收口：补"
type: "reference"
tags: [mcp-feedback, dev-toolkit]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T12:02:38.936059+00:00"
---

# MCP 使用反馈

## 任务

ContentPackage 到 Artifact 发布闭环最终收口：补强 capability/REST publish 契约测试，重启后端并完成活栈 artifact/file/download 验证与探针清理。

## 顺畅度

- 评分：4/5
- 体感：整体顺畅，brief/plan_task/codegraph/finish_task 对这类收口任务很有帮助。

## 本次用到的工具

brief
plan_task
worktree_guard
code_explore
code_node
code_impact
probe
call_capability
lint
finish_task
memory_write
mcp_feedback

## 卡点 / 不顺手的地方

worktree_guard 在并发脏工作区里需要手动整理较长 baseline_paths；lint 工具对目录路径 backend/app/services/content 误报文件不存在，但 shell ruff 可正常检查目录。

## 缺少的工具 / 能力

希望有一个“记录当前 dirty 为基线并返回 token/handle”的工具，后续 finish_task 可直接引用，避免复制长路径列表。

## 升级建议

lint 工具支持目录路径；finish_task 支持接收 worktree_guard 的输出 id 或自动沿用开工基线。

## 建议移除或合并的工具

无

## 其他备注

后端常驻服务可能未加载当前源码，活栈验证前重启后端能避免运行时代码与工作区代码不一致。

## 当前工具热度快照

```json
[
  {
    "tool": "code_node",
    "calls": 301,
    "error": 0,
    "avg_duration_seconds": 0.141
  },
  {
    "tool": "code_explore",
    "calls": 187,
    "error": 0,
    "avg_duration_seconds": 0.336
  },
  {
    "tool": "probe",
    "calls": 138,
    "error": 4,
    "avg_duration_seconds": 0.327
  },
  {
    "tool": "worktree_guard",
    "calls": 126,
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
    "calls": 99,
    "error": 0,
    "avg_duration_seconds": 0.75
  },
  {
    "tool": "sql",
    "calls": 99,
    "error": 4,
    "avg_duration_seconds": 0.03
  },
  {
    "tool": "plan_task",
    "calls": 97,
    "error": 0,
    "avg_duration_seconds": 0.006
  },
  {
    "tool": "code_impact",
    "calls": 96,
    "error": 0,
    "avg_duration_seconds": 0.129
  },
  {
    "tool": "finish_task",
    "calls": 63,
    "error": 0,
    "avg_duration_seconds": 1.547
  }
]
```
