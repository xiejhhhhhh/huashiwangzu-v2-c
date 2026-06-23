---
name: "工具台增强 + 规则统一 + agent 归因"
type: task
tags: ["mcp", "toolkit", "agents", "dedup"]
created: 2026-06-23
agent: opencode
---

## 做了什么

执行自包含任务文档 `投递箱/工具台增强+规则统一+agent归因(自包含).md`。

### 一、新增 6 个精度工具到 dev_toolkit/server.py

| 工具 | 功能 |
|------|------|
| code_explore | codegraph 代码探索, 查符号/调用链/影响面 |
| code_node | 查符号或文件定义 |
| code_impact | 查文件改动影响面 |
| lint | ruff 静态检查 Python 文件 |
| routes | 从 openapi.json 查准后端端点 |
| capabilities | 扫描 manifest.json 查模块能力 |
| db_schema | 查数据库表名/列类型 |
| run_test | 跑单个测试不跑全局 |

### 二、规则去重

将 AGENTS.md 定为项目规则唯一真相源, 通用约定.md 中 4 条重复规则改为引用 AGENTS.md。

### 三、agent 归因

- memory_write 新增 agent 参数写入 frontmatter
- brief() 新增"最近活动"段(最近 git log + 带 agent 的记忆)
- AGENTS.md 开工铁律更新为全流程

## 验收

- 15 工具全部真调通过
- lint 通过(ruff 0 错误)
- git diff 边界合规(无产品代码)
- memory frontmatter 含 agent: opencode

## 提交

`git commit` with Co-Authored-By
