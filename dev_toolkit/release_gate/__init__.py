"""Release gate CLI compatibility facade.

The implementation lives in ``dev_toolkit/release_gate/``. This file remains as
both the historical import target and the script path used by MCP/background jobs.
"""
from __future__ import annotations

import sys
import types

from dev_toolkit.process_tools import create_subprocess_exec_group, terminate_process_tree  # noqa: E402,F401
from dev_toolkit.release_gate import checks as _checks  # noqa: E402
from dev_toolkit.release_gate import context as _context  # noqa: E402
from dev_toolkit.release_gate import runner as _runner  # noqa: E402
from dev_toolkit.release_gate import smoke_gate as _smoke_gate  # noqa: E402
from dev_toolkit.release_gate.checks import (  # noqa: E402,F401
    check_asset_lifecycle_debt,
    check_capability_drift,
    check_component_key_contracts,
    check_docs_currentness,
    check_health,
    check_readme_acceptance_matrix,
    check_sandbox_matrix,
    check_system_status,
    check_task_queue_audit,
)
from dev_toolkit.release_gate.context import (  # noqa: E402,F401
    _TOKEN_MAX_AGE,
    ACCOUNTS,
    BACKEND_BASE,
    BACKEND_PYTHON,
    CONFIG,
    DB_DSN,
    FRONTEND_BASE,
    MODULES_DIR,
    RELEASE_GATE_CONFIG,
    SEMANTIC_COMPLETED_SCAN_LIMIT,
    _ensure_token,
    _project_python,
    _run_git,
    _token_cache,
    _url_status,
    audit_failed_count,
    changed_module_keys,
    collect_runtime_context,
    fetch_live_capabilities,
    fetch_task_queue_audit,
    git_snapshot,
    httpx,
    probe,
    results,
    runtime_context,
)
from dev_toolkit.release_gate.printers import (  # noqa: E402,F401
    _compact_items,
    add_result,
    build_release_summary,
    get_final_verdict,
)
from dev_toolkit.release_gate.smoke_gate import (  # noqa: E402,F401
    check_model_fallback_summary,
    check_smoke,
    check_ui_coverage,
    check_ui_smoke_summary,
)
from dev_toolkit.release_gate_support import (  # noqa: E402,F401
    _asset_marker_predicate,
    _task_result_is_semantic_failure,
    audit_content_package_lifecycle_debt,
    audit_knowledge_lifecycle_debt,
    audit_test_data_pollution,
    classify_capability_drift,
    classify_component_key_contracts,
    classify_readme_acceptance_matrix,
    classify_sandbox_matrix,
    classify_semantic_failed_completed,
    ensure_envelope_success,
    find_semantic_failed_completed_tasks,
    parse_prefixed_json,
    scan_manifest_public_actions,
    scan_source_registered_capabilities,
    semantic_failure_reason,
)

_PROPAGATED_ATTRS: dict[str, tuple[object, ...]] = {
    "BACKEND_PYTHON": (_context,),
    "create_subprocess_exec_group": (_checks, _smoke_gate),
    "terminate_process_tree": (_checks, _smoke_gate),
    "probe": (_context, _checks),
    "_ensure_token": (_context,),
    "fetch_task_queue_audit": (_context, _checks),
    "fetch_live_capabilities": (_context, _checks),
    "find_semantic_failed_completed_tasks": (_checks, _runner),
    "audit_knowledge_lifecycle_debt": (_checks,),
    "audit_content_package_lifecycle_debt": (_checks,),
    "audit_test_data_pollution": (_checks,),
    "classify_capability_drift": (_checks,),
    "classify_component_key_contracts": (_checks,),
    "classify_readme_acceptance_matrix": (_checks,),
    "classify_sandbox_matrix": (_checks,),
    "classify_semantic_failed_completed": (_checks,),
    "docs_audit": (_checks,),
    "ensure_envelope_success": (_checks,),
}


class _ReleaseGateFacade(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        for target in _PROPAGATED_ATTRS.get(name, ()):  # keep legacy monkeypatches effective
            setattr(target, name, value)


sys.modules[__name__].__class__ = _ReleaseGateFacade


async def main() -> None:
    await _runner.main(api=sys.modules[__name__])


def cli_main() -> None:
    _runner.cli_main(api=sys.modules[__name__])
