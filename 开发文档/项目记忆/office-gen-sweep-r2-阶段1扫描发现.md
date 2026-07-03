---
name: "office-gen sweep r2 阶段1扫描发现"
type: "task"
tags: [office-gen, module-sweep, heartbeat, scan, task_id:office-gen-sweep-20260703-r2]
agent: "codex-office-gen-sweep-20260703-r2"
created: "2026-07-03T06:57:48.824323+00:00"
---

阶段1扫描完成。证据：已读 开发文档/README.md、框架/底层/模块 README、modules/office-gen/README.md；已用 routes/capabilities/db_schema/code_explore/code_node/code_impact。发现候选问题：1) backend/generator.py 低层 generate_docx/xlsx/pptx/pdf 在空 content/sheets/slides 时仍产出合法空文件，存在空输出/假成功风险；能力层虽有 _require_non_empty_list，但直接 HTTP 复用能力层之外的低层测试仍鼓励空成功。2) Content IR 兼容不完整：_block_text 不读 data.text/title，表格不读 data.headers/data.columns，presentation 不支持 top-level slide block 的 children 与 data.title，spreadsheet 不支持 Content IR top-level sheet blocks + children table/range。3) converter 只检查输出存在，不检查转换输出非空。4) manifest public_actions 仍只描述 legacy 参数，未声明 Content IR blocks/sheets/slides 别名，存在能力声明漂移。待修复范围限定 modules/office-gen/**。
