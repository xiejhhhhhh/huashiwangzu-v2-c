---
name: "r1-节点1-修复 insight_tools 自检盲区"
type: "task"
tags: [dev-toolkit, r1, insight-tools, self-check]
agent: "opencode-r1-devtool"
created: "2026-07-03T05:10:00.548689+00:00"
---

1. 修复 `_direct_server_tools` 正则错误: 原代码查找 `Tool(name=...)` 但 server.py 不直接定义 Tool()，永远返回空列表。替换为 `_wired_component_tools()` 读取 server.py import 别名 + list_tools 注册 + call_tool 调度分支，判断组件是否完全接线。
2. 新增 `_orphan_component_tools()` 检测已声明但未接线到 server.py 的工具（运行时返回 404）。
3. 更新 `mcp_self_check` 输出：添加 wired_components 和 orphan_tools 字段；success 条件含 orphan_tools 为空。
4. 测试覆盖：验证 wired_components 中 core_tools 和 opencode_tools 均 wired=true, orphan_tools 为空。
