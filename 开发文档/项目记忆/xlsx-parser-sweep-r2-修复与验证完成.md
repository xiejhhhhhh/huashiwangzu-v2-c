---
name: "xlsx-parser sweep r2：修复与验证完成"
type: "task"
tags: [xlsx-parser, module-sweep, r2, complete, verification, task_id:xlsx-parser-sweep-20260703-r2]
agent: "codex-xlsx-parser-sweep-20260703-r2"
created: "2026-07-03T07:44:45.658265+00:00"
---

完成 modules/xlsx-parser 模块级扫雷。问题与修复：1) 后端解析逻辑原来内嵌在 router，sandbox 复制另一套简化逻辑，已抽出 backend/parser_core.py 并让 sandbox 复用；2) 原声明允许 .xls 但 openpyxl 实际不支持，已改为只允许 xlsx/csv 并更新 README；3) file_id<=0/坏 xlsx 原会沿 ValueError/解析异常走 500，router 现转换为 ValidationError，成功路径仍通过 run_uploaded_file_capability/check_file_access；4) CSV 与 XLSX block type 统一为 table，XLSX sheet page 改为 1-based sheet index；5) 空工作簿/空 CSV 明确返回空 blocks + warnings，公式无缓存值时保留公式文本，大文件按 5000 非空行截断。改动文件：modules/xlsx-parser/backend/parser_core.py、backend/router.py、sandbox/test_module.py、README.md、manifest.json。验证：ruff 全过；mcp run_test pytest 1 passed；sandbox 脚本直跑 PASS；sandbox npm run build PASS；/api/health PASS；活栈 call_capability file_id=2018 PASS 但常驻进程仍是旧代码(page:null)，直接导入新 router 验证 file_id=0 -> ValidationError。测试数据：临时公式/空/大/坏 xlsx 全用 tempfile.TemporaryDirectory 自动清理，没有新增 data/uploads。残留风险：需要后端重载后再用 call_capability 验证新 page/warnings/错误语义在线生效；仓库存在其他 agent 的并发脏改动，本任务未触碰。
