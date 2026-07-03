---
name: "structured-parser sweep r2 fixes and validation complete"
type: "task"
tags: [structured-parser, r2, parser, sandbox, validation, file-access]
agent: "codex-structured-parser-sweep-20260703-r2"
created: "2026-07-03T08:03:24.058089+00:00"
---

Completed structured-parser r2 sweep. Fixed production parser structure by extracting modules/structured-parser/backend/parser.py and keeping router.py as framework/capability adapter. The parser now handles JSON/YAML/yml with explicit empty summaries, stable root scalar path, 2 MiB size gate, emitted-field cap, GBK/framework text decoding, English content block types, metadata, and structured parser exceptions. Router now validates HTTP file_id with Field(gt=0), maps bad capability file_id ValueError/TypeError to ValidationError, maps parser failures to ValidationError and oversized files to 413 AppException, while still using run_uploaded_file_capability for framework check_file_access and path safety. Sandbox now imports production parser/router code and covers sample JSON, sample YAML, empty file, empty object, scalar root, GBK JSON, invalid JSON/YAML, oversized file, and bad file_id mapping. Verification: ruff passed for parser.py/router.py/sandbox test; run_test pytest sandbox passed 10 tests; direct script sandbox passed; /api/structured-parser/health live probe returned 200. Live call_capability bad file_id returned 500 because the shared backend process had not reloaded the modified module code; not restarted due concurrent dirty work from other agents, so reprobe after backend reload.
