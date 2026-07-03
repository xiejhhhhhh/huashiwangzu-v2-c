---
name: "text-parser sweep r2：修复进展与验证节点"
type: "task"
tags: [text-parser, module-sweep, r2, parser, file-access, sandbox, verification, task_id:text-parser-sweep-20260703-r2]
agent: "codex-text-parser-sweep-20260703-r2"
created: "2026-07-03T07:50:09.523905+00:00"
---

已在 modules/text-parser 内完成修复：新增 backend/parser.py，将真实解析逻辑从 router 拆出供 sandbox 复用；router.py 保留框架 run_uploaded_file_capability 权限通路，并将 file_id/解析格式 ValueError/TextParseError 转为 ValidationError，能力参数补齐 description；parser 增加空文件成功空 blocks、GBK/GB18030 解码、大文件 MAX_TEXT_BYTES 截断元数据；sandbox/test_module.py 改为 pytest，直接加载 backend/parser.py 并覆盖真实 sample.txt/sample.md、空文件、GBK、截断、unsupported format。验证：ruff 3 文件通过；sandbox pytest 6 passed；sandbox npm run build 通过；compileall + git diff --check 通过；活栈 health 200。活栈 call_capability(file_id=0) 返回 500，判断为常驻后端未重启仍使用旧注册函数，未报假绿。
