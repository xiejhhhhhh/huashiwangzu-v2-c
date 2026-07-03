---
name: "csv-parser sweep r2 parser fixes checkpoint"
type: "task"
tags: [csv-parser, sweep, parser, sandbox, task_id:csv-parser-sweep-20260703-r2]
agent: "codex-csv-parser-sweep-20260703-r2"
created: "2026-07-03T07:49:50.292425+00:00"
---

已在 modules/csv-parser/backend/router.py 抽出 parse_csv_content/parse_csv_path，修复 CSV 解析边界：file_id 先转 ValidationError；BOM 清理；TSV/逗号/分号/pipe 分隔符检测；csv.reader(strict=True) 捕获畸形 CSV 并抛 ValidationError；空文件返回明确空表块；大表不再 list(reader) 整表入内存，最多输出前 1000 数据行并在摘要说明省略。sandbox/test_module.py 改为直接导入生产 parser，覆盖真实 sample.csv/sample.tsv、GBK+分号、空文件、大表截断、畸形 CSV、非法 file_id。ruff 与 pytest 初跑已通过。
