---
name: "docx-parser sweep r2 修复与验证完成"
type: "task"
tags: [docx-parser, module-sweep, r2, parser, file-access, false-success, sandbox, verification, task_id:docx-parser-sweep-20260703-r2]
agent: "codex-docx-parser-sweep-20260703-r2"
created: "2026-07-03T07:43:22.655917+00:00"
---

本轮完成 modules/docx-parser 扫雷和修复。发现：后端 parse 已经通过框架 run_uploaded_file_capability 走 file_id 权限通路（内部调用 read_uploaded_file/check_file_access），没有直接裸读 File；manifest public_actions 与 register_capability 基本一致，但 register 参数缺描述；sandbox/test_module.py 复制了一份简化解析器，返回中文 block type，未测试真实后端解析逻辑、图片、空文档和 corrupt 文档失败语义；README 缺模块 sandbox 可复现验收命令。修复：新增 modules/docx-parser/backend/parser.py，把纯 DOCX 解析抽成模块内共享函数 parse_docx_file；router 改为调用该函数，HTTP ParseRequest 加 file_id > 0，register_capability 参数描述与 manifest 对齐；解析按 doc.element.body 顺序处理段落/表格，并在段落位置识别内联图片 rel，提取 bytes_b64 交给框架资源诊断/存储助手；sandbox/test_module.py 改为导入真实 parser，覆盖真实 sample.docx、动态生成含图片 docx、空 docx、坏 docx 抛错，临时文件用 TemporaryDirectory 自动清理；README 补权限通路/失败语义说明和 ruff/pytest/sandbox build 命令。验证：ruff 通过；mcp run_test modules/docx-parser/sandbox/test_module.py 4 passed；手动 PYTHONPATH=backend pytest 4 passed；sandbox 脚本通过；modules/docx-parser/sandbox npm run build 通过（仅 Rollup chunk size 常规 warning）；probe /api/docx-parser/health success；call_capability docx-parser:parse file_id=1 success:true 返回 paragraph/table blocks；file_id=0 返回 success:false，不是假成功；本地 import_module_router 装载 /api/docx-parser 成功。测试数据：仅使用 TemporaryDirectory 临时生成 docx/png/broken 文件并自动清理；未上传新文件，未修改 data/uploads。残留：worktree_guard 因并发/既有 data/uploads、docs-open、pdf-parser、xlsx-parser 等改动仍报红，本任务未触碰；活栈未重启，已用本地 router 装载验证新代码可加载。
