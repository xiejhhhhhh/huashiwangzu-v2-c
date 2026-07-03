---
name: "xlsx-parser sweep r2：核心解析修复与验证进展"
type: "task"
tags: [xlsx-parser, module-sweep, r2, parser, file-access, sandbox, task_id:xlsx-parser-sweep-20260703-r2]
agent: "codex-xlsx-parser-sweep-20260703-r2"
created: "2026-07-03T07:44:24.558083+00:00"
---

阶段修复已落盘在 modules/xlsx-parser/**：新增 backend/parser_core.py 作为纯解析核心；router.py 保持 run_uploaded_file_capability 文件访问通路，并把 file_id/解析错误转换为 ValidationError；移除实际不可支持的 .xls 解析承诺，仅支持 xlsx/csv；解析输出统一 table 类型，sheet page 使用 1-based sheet index，空工作簿/空 CSV 返回空 blocks 并带 warnings；公式无缓存值时保留公式文本；每 sheet/CSV 限 5000 个非空输出行并带截断标记。sandbox/test_module.py 改为复用真实 parser_core，覆盖真实 sample.xlsx/sample.csv、多 sheet、公式、空工作簿、大文件截断、坏 xlsx 失败，并新增 pytest 入口。已通过 ruff、sandbox 脚本、pytest 包装、sandbox npm build、/api/health；活栈 call_capability 解析现有 file_id=2018 成功但返回旧 page:null，说明常驻后端尚未重载新模块代码，未为避免越界写日志而重启。
