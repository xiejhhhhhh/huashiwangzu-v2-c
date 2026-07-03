# office-gen — Office document generator

## Responsibility

Generates and converts office documents (`docx`, `xlsx`, `pptx`, `pdf`) from structured JSON data. Generation uses `python-docx`, `openpyxl`, `python-pptx`, and `reportlab`; conversion uses LibreOffice headless. File outputs are persisted through the framework file/artifact services, while this module owns only its generation and conversion logic.

## Public Capabilities

8 capabilities are registered through the framework capability registry.

| Capability | Parameters | Returns | min_role |
|---|---|---|---|
| `office-gen:docx` | `filename`, non-empty `content` or Content IR `blocks`/`content_ir`, optional `folder_id` | framework file info `{file_id, name, extension, size, mime_type, deduplicated}` | editor |
| `office-gen:xlsx` | `filename`, non-empty `sheets` or Content IR sheet `blocks`/`content_ir`, optional `folder_id` | framework file info | editor |
| `office-gen:pptx` | `filename`, non-empty `slides` or Content IR slide `blocks`/`content_ir`, optional `folder_id` | framework file info | editor |
| `office-gen:pdf` | `filename`, non-empty `content` or Content IR `blocks`/`content_ir`, optional `folder_id` | framework file info | editor |
| `office-gen:convert` | `file_id`, `target_format` | new framework file info | editor |
| `office-gen:generate_to_artifact` | `format`, `filename`, matching non-empty `content`/`sheets`/`slides`, optional `folder_id` | `{artifact_id, file_id, content_package_id, content_package_status, content_package_error, format, name, extension, size, status}` | editor |
| `office-gen:replace_existing` | `format`, `target_file_id`, matching non-empty `content`/`sheets`/`slides` | `{file_id, content_package_id, content_package_status, content_package_error, name, size, format, status}` | editor |
| `office-gen:export_to_artifact` | `file_id` | `{artifact_id, file_id, content_package_id, name, extension, size}` | editor |

Content blocks accept both legacy Chinese block names and Content IR English block names:

```text
heading/标题, paragraph/段落, list, code, table/表格, image/图片, page_break/分页
```

Table aliases:

```text
header/table_header/表头
rows/table_rows/行
data.headers/data.columns + data.rows
```

XLSX sheets accept string columns, Content IR-style column objects such as `{name: "amount"}`, or spreadsheet IR blocks shaped as `sheet.children[].table`. PPTX slides accept normal `{title, bullets}`, `{name, elements}`, or presentation IR `slide.children`.

The low-level generators and capability entrypoints reject empty `content`/`sheets`/`slides` and blocks that render no text/table/image content. Conversion also rejects zero-byte LibreOffice outputs, so successful responses should always point at a non-empty artifact or framework file.

## HTTP Endpoints

HTTP endpoints are for direct testing and sandbox use. Artifact-only capabilities are capability-registry only.

All HTTP routes are under `/api/office-gen`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check and LibreOffice availability |
| POST | `/docx` | Generate Word document |
| POST | `/xlsx` | Generate Excel spreadsheet |
| POST | `/pptx` | Generate PowerPoint presentation |
| POST | `/pdf` | Generate PDF document |
| POST | `/convert` | Convert between office formats |

## Content IR And Artifact Boundary

- `docx/xlsx/pptx/pdf` generate physical framework files through `upload_file`.
- `convert` validates file access through `read_uploaded_file`, which wraps `check_file_access`, extension validation, storage path resolution, and path traversal protection before LibreOffice reads the source path.
- `generate_to_artifact` creates a framework artifact through `create_artifact`, then attempts to create/parse a Content Package for the generated file.
- `replace_existing` updates an existing framework file through `replace_file_content`, which enforces framework write access, then attempts to refresh the associated Content Package.
- Content Package sync is explicit in returned fields: `content_package_status` is `parsed`, `degraded`, `partial`, `failed`, or another framework status. A generated file/artifact can still be created while parsing fails; in that case `content_package_status="failed"` and `content_package_error` is populated.
- `export_to_artifact` checks file access before reading bytes or looking up an accessible Content Package.
- Framework Content IR services remain owned by `backend/app/services/content/*`; required changes there must be raised as framework tasks, not made in this module.

## Data Tables

None owned by this module. Outputs are stored in framework tables:

```text
framework_file_items
framework_artifacts
framework_artifact_versions
framework_artifact_operations
framework_content_packages
framework_content_package_versions
```

## Validation

Run from the repository root:

```bash
backend/.venv/bin/python modules/office-gen/sandbox/test_module.py
cd backend && .venv/bin/python -m pytest ../modules/office-gen/tests/test_generator.py -v
cd backend && .venv/bin/python -m ruff check ../modules/office-gen/backend ../modules/office-gen/tests ../modules/office-gen/sandbox
```

Live-stack checks should use the project toolkit:

```text
capabilities(module="office-gen")
probe("GET", "/api/office-gen/health", role="editor")
call_capability("office-gen", "docx", {"filename":"...", "content":[...]}, role="editor")
```

Generated live-stack test files must be cleaned up by the creator after verification.

## Known Follow-Up Outside This Module

- Framework Content IR export currently decides fallback behavior in `backend/app/services/content/export_service.py`. If product policy requires Content Package parsing failure to fail the whole artifact operation instead of returning an explicit `content_package_status="failed"`, that should be handled as a separate framework task.
