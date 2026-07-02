---
name: "foundation-upgrade-scout-r2节点4-工具台自检小修验证"
type: "reference"
tags: [foundation-upgrade-scout-r2, upgrade-scout, 节点4, dev-toolkit, small-fix]
agent: "foundation-upgrade-scout-r2"
created: "2026-07-02T16:20:37.679212+00:00"
---

发现完整小链路：mcp_self_check/dev_toolkit_architecture_audit 在真实 MCP stdio 脚本路径下返回 No module named dev_toolkit。原因是 insight_tools 动态 import 组件时只尝试 dev_toolkit.{component}，而 server.py 以脚本方式运行时可落入顶层模块导入。已小修为 ModuleNotFoundError 时回退到同目录模块名；验证 python3.14 -m pytest dev_toolkit/test_insight_tools.py 3 passed，真实 MCP stdio 调用 mcp_self_check(include_tools=false) 返回 success:true。
