---
name: "email-parser sweep r2 fixes and validation"
type: "task"
tags: [email-parser, sweep, r2, validation, file-access, false-success, sandbox]
agent: "codex-email-parser-sweep-20260703-r2"
created: "2026-07-03T08:02:31.842706+00:00"
---

Completed modules/email-parser r2 sweep fixes inside module boundary. Findings fixed: file access path already uses run_uploaded_file_capability -> read_uploaded_file -> check_file_access; bad file_id now becomes ValidationError before runner ValueError can leak; parsing logic moved to backend/parser.py and rejects empty/non-email EML instead of accepting plain garbage as body; EML plaintext/HTML fallback extraction avoids duplicate alternative bodies; attachments now return unified resource fields with mime_type/filename/description/text_desc/_bytes_b64 and router passes results through store_extracted_resources_with_diagnostics; sandbox now imports production parser.py and covers sample EML, HTML-only body, attachment bytes/resources, and bad EML rejection; README added with reproducible verification commands. Verification: ruff passed for router.py/parser.py/sandbox/test_module.py; sandbox script passed; run_test modules/email-parser/sandbox/test_module.py passed 1 test; /api/email-parser/health probe returned 200. Live call_capability email-parser:parse file_id=0 still returned 500, but local import of the new router confirmed ValidationError, so this is treated as stale always-on backend registration until service reload.
