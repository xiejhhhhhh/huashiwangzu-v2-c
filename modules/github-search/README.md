# github-search

## Responsibility

`github-search` is a background capability service in the V2 desktop/module architecture. It is declared by `manifest.json` and must be consumed through the framework runtime, HTTP router, or capability registry rather than direct cross-module imports.

## Public Capabilities

| Capability | min_role | Notes |
|---|---|---|
| `github-search:search` | viewer | 搜索 GitHub 开源项目，按活跃度和质量排序。输入关键词即可，自动过滤归档和不活跃项目。 |
| `github-search:search_code` | viewer | 在 GitHub 上搜索代码片段。返回包含匹配代码的文件路径和仓库信息。 |

## Boundaries

- Business logic stays inside this module directory.
- Cross-module access must go through the framework capability registry or runtime SDK.
- Framework file content access must preserve `check_file_access` semantics when `file_id` is used.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `github-search`, window `background-service`, formats: Not format-bound. |
| Backend capability | PASS | 2 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Background service is intentionally hidden from launcher with empty component_key. |
| File access | SKIP | Module does not directly consume framework file_id content. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/github-search/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `github-search:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep component_key empty so the launcher never opens a blank background window. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/github-search/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module github-search --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
