---
name: "能力契约漂移收口与 contract scanner 修正 r4"
type: "task"
tags: [contract-drift, dev-toolkit, mcp, agent, desktop-tools, image-gen, r4]
agent: "codex-conductor-r4"
created: "2026-07-03T11:23:29.732248+00:00"
---

# 改了什么
- 修正 dev_toolkit capability_contract_diff 对静态 capabilities 表的解析：tuple 第 6 位才是 parameters，并忽略已由静态表解析覆盖的循环 register_capability 动态调用误报。
- 恢复 agent/bootstrap.py 正常 register_capability import/call，避免产品代码为了工具误报而起别名。
- 对齐 agent、desktop-tools、image-gen 的 manifest/runtime 参数元数据。

# 验证
- ruff 通过。
- dev_toolkit/test_contract_tools.py + mcp self-check 相关测试：6 passed。
- 全仓 capability_contract_diff(include_parameters=True)：0 drift / 0 uncheckable。
- desktop-tools sandbox、image-gen sandbox、agent task registration：13 passed（使用 pytest --import-mode=importlib 避免同名 sandbox/test_module.py 冲突）。

# 结论
这是工具台与模块契约共同收口：以后不需要通过扭曲产品代码绕过 scanner。
