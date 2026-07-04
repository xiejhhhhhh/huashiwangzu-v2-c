---
name: "Parser Content IR 收口：docx/pdf/pptx"
type: "task"
tags: [parser, content-ir, docx-parser, pdf-parser, pptx-parser, sandbox]
agent: "codex-subagent-c"
created: "2026-07-04T14:29:51.736953+00:00"
---

子代理 C 完成 docx-parser/pdf-parser/pptx-parser Content IR 收口。三模块输出保留 legacy file_id/format/page/resource_ref，同时补 schema_version=content-ir/v1、content_type、source/source_file_id/source_module/parser、metadata/warnings、block/resource source_ref；pptx 顶层改为 slide blocks，子块保留 heading/paragraph/image。Sandbox 升级为检查 schema_version、非空 blocks、source_ref，并调用现有 normalize_ir。矩阵：docx legacy blocks/resources -> IR compatible yes，缺页码(库不可得，source_ref 用 paragraph/table)；pdf legacy blocks/resources -> yes，source_ref page/xref；pptx flat text/image -> yes，改 slide 顶层，source_ref slide/shape。验收：ruff passed；sandbox scripts passed；pytest 分模块 docx 4/pdf 2/pptx 1 passed；Content IR architecture 62 passed；module_sandbox_matrix 三模块 --check PASS。未提交 commit。开工时 worktree clean，收尾时出现范围外并行 dirty，未触碰未回退。
