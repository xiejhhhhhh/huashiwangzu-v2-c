---
name: "structured-parser sweep r2 evidence and repair checkpoint"
type: "task"
tags: [structured-parser, r2, parser, sandbox, validation]
agent: "codex-structured-parser-sweep-20260703-r2"
created: "2026-07-03T08:02:12.737953+00:00"
---

Evidence gathered with codegraph/code_node/code_impact plus routes/capabilities/db_schema. Findings: router contained parser closure, sandbox duplicated simplified JSON-only logic, capability bad file_id could bubble ValueError/TypeError as 500, empty structured inputs returned empty blocks, large files had no module size gate, root scalar path rendered as empty prefix. Repairs in progress: extracted backend/parser.py, router now maps parser errors and bad file_id to structured AppException/ValidationError, sandbox now tests production parser JSON/YAML/empty/bad/large/GBK/scalar and router bad file_id path.
