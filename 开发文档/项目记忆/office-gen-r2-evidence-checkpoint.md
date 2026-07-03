---
name: "office-gen r2 evidence checkpoint"
type: "task"
tags: [office-gen, r2, evidence, contract, sandbox]
agent: "codex-office-gen-followup-sweep-20260703-r2"
created: "2026-07-03T08:03:53.281156+00:00"
---

Evidence checkpoint for office-gen r2 sweep. Used code_explore/code_node/code_impact plus routes/capabilities/db_schema and module README. Findings to repair under modules/office-gen only: capability/HTTP parameter validation can let bad file_id/target_file_id/target_format or LibreOffice conversion RuntimeError escape as unstructured 500; backend register_capability JSON schemas and HTTP Pydantic request models lag manifest/README by not exposing blocks/content_ir aliases; sandbox only exercises generator.py and misses production router/capability validation; frontend card click handler is a no-op empty implementation despite clickable cards.
