---
name: "csv-parser sweep r2：修复与验证完成"
type: "task"
tags: [csv-parser, module-sweep, r2, complete, verification, task_id:csv-parser-sweep-20260703-r2]
agent: "codex-csv-parser-sweep-20260703-r2"
created: "2026-07-03T07:51:24.107565+00:00"
---

完成 modules/csv-parser 模块级扫雷与修复。问题与修复：1) file_id 非法参数先在模块内转为 ValidationError，避免 runner 的 ValueError 变成 500；2) CSV 解析从 content.strip().splitlines()+list(reader) 改为 StringIO + csv.reader(strict=True) 流式遍历，畸形 CSV 抛 ValidationError，不假成功；3) 分隔符检测支持 TSV、逗号、分号、pipe，并清理 UTF-8 BOM；4) 空文件返回明确空表块；5) 大表最多输出前 1000 数据行，摘要保留总行数与省略说明，避免输出无限膨胀；6) sandbox 直接导入生产 parser，覆盖真实 sample.csv/sample.tsv、GBK+分号、空文件、大表截断、畸形 CSV、非法 file_id。权限通路核实：run_uploaded_file_capability -> read_uploaded_file -> app.services.file_service.check_file_access，符合 file_id 访问控制要求。manifest public_actions 与 register_capability 均为 csv-parser:parse(file_id), min_role=viewer，保持一致。验证：ruff check router.py/test_module.py 通过；PYTHONPATH=backend backend/.venv/bin/python -m pytest modules/csv-parser/sandbox -q：7 passed；直接运行 sandbox/test_module.py 通过；重启后端健康；probe /api/health 与 /api/csv-parser/health 成功；call_capability csv-parser:parse file_id=0 返回 422 success:false。未做上传正向活栈解析，因为会新增 data/uploads，任务明确禁止修改 data/uploads；库中无现成 CSV/TSV 文件可复用。工作区存在其他 agent 的 data/uploads、docx/text/xlsx 等脏改动，未触碰。关联 commit：未提交。
