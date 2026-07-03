---
name: "text-parser sweep r2：修复与验证完成"
type: "task"
tags: [text-parser, module-sweep, r2, complete, verification, task_id:text-parser-sweep-20260703-r2]
agent: "codex-text-parser-sweep-20260703-r2"
created: "2026-07-03T07:51:30.154119+00:00"
---

完成 modules/text-parser 模块级扫雷与必要修复。问题：router 内嵌解析逻辑导致 sandbox 只测复制品；file_id 非正数 ValueError 未转统一 ValidationError；大文件整读且无截断元数据；sandbox 缺空文件/编码/截断/失败路径覆盖；README 缺可复现 sandbox/pytest 验收。修复：新增 modules/text-parser/backend/parser.py，提供 SUPPORTED_EXTS、parse_text_file/parse_text_bytes、空文件空 blocks、GB18030/GBK 解码、MAX_TEXT_BYTES+4 安全边界、metadata(original_size/parsed_bytes/max_bytes/truncated/encoding)；router.py 使用 parser.py，保留 run_uploaded_file_capability -> read_uploaded_file -> check_file_access 权限通路，TextParseError/ValueError 转 ValidationError，ParseRequest Field(gt=0)，能力参数 description 与 manifest 对齐；sandbox/test_module.py 改 pytest 并直接加载 backend/parser.py；README 补权限说明、截断语义、ruff/pytest/sandbox build 命令。验证：ruff 通过；sandbox pytest 6 passed；sandbox npm run build 通过；compileall 与 git diff --check 通过；codegraph impact 仅 text-parser；probe /api/text-parser/health 200。call_capability text-parser:parse file_id=0 在常驻后端返回 500，未重启后端，判断为旧注册函数仍在内存，需重启后复探新 ValidationError 语义。测试数据：pytest 使用 tmp_path 自动清理；未新增 data/uploads。边界：本任务改动为 modules/text-parser/README.md、modules/text-parser/backend/router.py、modules/text-parser/backend/parser.py、modules/text-parser/sandbox/test_module.py，以及本任务项目记忆/反馈；工作区另有并行 agent 的 data/uploads、csv/docx/xlsx 等既有改动，未触碰未回退。
