---
name: "工具台 capability_contract_diff 契约漂移扫描器 r4"
type: "task"
tags: [dev-toolkit, capability-contract, manifest, runtime, r4]
agent: "codex-conductor-r4"
created: "2026-07-03T11:07:16.568064+00:00"
---

# 改了什么
新增 dev_toolkit capability_contract_diff 组件工具，用 AST 扫描 modules/*/backend/**/register_capability 与 manifest.json public_actions，比较 action、min_role 与参数 key 漂移，并接入 dev_toolkit/server.py 的工具注册与分发。

# 验证了什么
- codegraph explore 查看 contract_tools 与 server wiring 影响面。
- ruff check dev_toolkit/contract_tools.py dev_toolkit/test_contract_tools.py dev_toolkit/server.py 通过。
- pytest dev_toolkit/test_contract_tools.py + mcp_self_check 两个组件契约测试，5 passed。

# 残留风险
该工具本身是扫描器；当前仓库仍存在真实契约漂移，已派 contract lane worker 按大域治理。
