---
name: "Parser Content IR 全解析器权威归一总收口"
type: "task"
tags: [parser, content-ir, audit, normalizer, sandbox]
agent: "codex-parser-ir-conductor"
created: "2026-07-04T14:36:12.395528+00:00"
---

### Parser Content IR 全解析器权威归一总收口（2026-07-04）
- 做了什么：11 个 parser/vision/media 模块补齐 Content IR 兼容 envelope、block/resource source_ref，并在框架 `normalize_parser_output()` 中增加 legacy parser 输出到 canonical Content IR 的统一适配入口。
- 改了哪些：`backend/app/services/content/ir_normalizer.py`、`backend/tests/test_content_ir_architecture.py`、`modules/{text,markdown,csv,xlsx,docx,pdf,pptx,email,structured}-parser/`、`modules/image-vision/`、`modules/media-intelligence/`。
- Parser IR 矩阵：

| module | current output | IR compatible | missing fields | action |
|---|---|---:|---|---|
| text-parser | legacy blocks/resources + IR top-level fields | YES | filename/mime_type parser core unavailable | Added title, source/source_file_id/source_module/parser/warnings and line-based source_ref; empty file emits explicit paragraph. |
| markdown-parser | legacy blocks/resources + IR top-level fields | YES | filename/mime_type unavailable | Added title, mixed content envelope, line/section source_ref, image resource source_ref, explicit empty block. |
| csv-parser | legacy table blocks + IR top-level fields | YES | filename unavailable | Added title/source metadata, row/line source_ref, warnings/metadata; framework adapter reshapes to spreadsheet IR. |
| xlsx-parser | legacy table blocks + IR top-level fields | YES | filename unavailable | Added title/source metadata, sheet/range source_ref, explicit empty sheet/workbook blocks; framework adapter reshapes to spreadsheet IR. |
| docx-parser | document blocks/resources + IR fields | YES | DOCX page numbers unavailable | Added title/source metadata, paragraph/table/resource source_ref, image resource_type/data_b64. |
| pdf-parser | document blocks/resources + IR fields | YES | none for page-level tracing | Added title/source metadata, page/table/image xref source_ref, image resource_type/data_b64. |
| pptx-parser | presentation slide tree + IR fields | YES | none for slide-level tracing | Changed flat blocks to slide blocks with children; added slide/shape/resource source_ref. |
| email-parser | mixed blocks/resources + IR fields | YES | no universal email line numbers | Added title/source metadata, header/body/attachment source_ref and attachment resource tracing. |
| structured-parser | text blocks/resources + IR fields | YES | no physical line preservation | Added title/source metadata, summary/data/path source_ref and field ranges. |
| image-vision | image analysis output + IR fields | YES | none for image facts | Added image Content IR builder, image/resource source_ref, quality/strategy metadata. |
| media-intelligence | media analysis output + IR fields | YES | ASR/keyframe external adapters may be degraded | Added Content IR blocks/resources/source_ref for image/video/summary/degraded cases; module schema version preserved in metadata. |

- 验证了什么：ruff 全部相关 Python 通过；`backend/tests/test_content_ir_architecture.py` 63 passed；目标 11 模块 `module_sandbox_matrix --check` 11 pass / 0 fail / 0 skip。
- 残留问题：工作区存在并行任务外 dirty 文件，未纳入本任务提交；media-intelligence 的真实 OCR/ASR/keyframe 仍取决于外部适配器可用性，当前通过 degraded/source_ref 保留证据。
