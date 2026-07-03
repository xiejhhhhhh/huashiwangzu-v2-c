---
name: "r1-节点2-提取共同Sdk助手+PTY拆分+queue引用公用"
type: "task"
tags: [dev-toolkit, r1, opencode, common, pty-split]
agent: "opencode-r1-devtool"
created: "2026-07-03T05:19:36.072687+00:00"
---

1. 创建 opencode_common.py: 提取 opencode_tools.py 和 opencode_queue.py 重复的路径/常量/环境 helper（now_slug, safe_title, opencode_env, node/npm binary, 路径函数）到共享模块。
2. 更新 opencode_queue.py: 删除重复定义, 从 opencode_common 导入; 删除废 import os/shutil/datetime(timezone); 添加 try/except ModuleNotFoundError 兜底。
3. 创建 opencode_pty_tools.py: 从 1295 行的 opencode_tools.py 拆分 PTY 会话函数(pty_start/read/write/stop) + 独立组件三件套(tool_definitions/handles_tool/handle_tool)。
4. 更新 opencode_tools.py: 删除 PTY 函数/状态/imports; 从 opencode_common 导入 _opencode_env/_safe_title/_now_slug; 从 1295 行降至 981 行（<1000）。
5. 更新 server.py: 添加 opencode_pty_tools 组件接线(import + list_tools + call_tool)。
6. 测试: 16/16 通过（test_opencode_tools 11 + test_insight_tools 3 + test_mcp_entry 2）。
7. ruff lint: All checks passed。
