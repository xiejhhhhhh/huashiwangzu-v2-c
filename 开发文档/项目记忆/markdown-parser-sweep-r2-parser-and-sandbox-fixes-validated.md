---
name: "markdown-parser sweep r2 parser and sandbox fixes validated"
type: "task"
tags: [markdown-parser, r2, sweep, validation, sandbox, file_id]
agent: "codex-markdown-parser-sweep-20260703-r2"
created: "2026-07-03T08:00:20.975169+00:00"
---

完成 markdown-parser r2 修复节点：1) 生产 parse 入口新增 file_id 正整数校验，file_id=0/-1/非数字/bool/None 在模块内转 app.core.exceptions.ValidationError，避免 ValueError 逃逸为 500；2) 抽出 parse_markdown_content 供生产和 sandbox 共用；3) 修复 fenced code 关闭围栏不识别导致后续内容吞进 code block 的问题；4) 修正多列表格分隔行识别，保持统一 block shape；5) sandbox/test_module.py 删除影子 parser，改为 importlib 加载生产 router.py，并同时支持脚本与 pytest；6) sample.md 补代码块、表格、图片覆盖。验证：ruff check router.py/test_module.py 通过；backend/.venv/bin/python modules/markdown-parser/sandbox/test_module.py 通过；run_test modules/markdown-parser/sandbox/test_module.py 2 passed。活栈 health ok；共享后端未热加载本次模块代码，file_id=0 探针仍命中旧 500，因此未在并行 agent 环境下擅自重启。
