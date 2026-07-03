---
name: "pptx-parser sweep r2 parser and sandbox fixes checkpoint"
type: "task"
tags: [pptx-parser, sweep, parser, sandbox, r2]
agent: "codex-pptx-parser-sweep-20260703-r2"
created: "2026-07-03T07:52:16.549977+00:00"
---

Agent codex-pptx-parser-sweep-20260703-r2 applied scoped fixes under modules/pptx-parser only. backend/router.py now validates file_id as a positive integer for both HTTP and capability entrypoints, wraps python-pptx Presentation load failures in framework ValidationError, and uses MSO_SHAPE_TYPE.PICTURE instead of string matching shape_type. sandbox/test_module.py now imports the real backend router, stubs framework file/resource helpers, validates real sample output, and checks non-positive file_id plus invalid PPTX bytes raise ValidationError.
