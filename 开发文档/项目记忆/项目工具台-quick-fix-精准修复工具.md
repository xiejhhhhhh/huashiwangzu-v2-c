---
name: "项目工具台 quick_fix 精准修复工具"
type: architecture
tags: ["dev-toolkit", "mcp", "codegraph", "quick-fix"]
created: 2026-06-27
agent: codex
---

新增 dev_toolkit quick_fix 能力: quick_fix_preview / quick_fix_patch。推荐 CodeGraph 定位源码与行号后, 用 old_text/new_text 精确替换；preview 返回 diff 不写盘，patch 同校验后原子写盘。安全边界: 路径必须在仓库内，拒绝 .git/node_modules/虚拟环境/__pycache__/废弃或旧目录；old_text 必须唯一命中，重复命中需传 start_line/end_line 收窄；可传 expected_old_text_sha256 防漂移。验证: backend/.venv/bin/python -m pytest dev_toolkit/test_quick_fix.py -q, backend/.venv/bin/ruff check dev_toolkit/quick_fix.py dev_toolkit/server.py dev_toolkit/test_quick_fix.py, py_compile, 工具注册和临时文件 preview/patch 冒烟均通过。
