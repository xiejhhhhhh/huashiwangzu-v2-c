"""Tests for the codemap module — graph, parser, boundary engine.

These tests create temporary project structures, build the code graph,
and verify all query capabilities.

Run from project root:
  cd backend && .venv/bin/python -m pytest ../modules/codemap/tests/test_codemap.py -v
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# ── Properly set up codemap.backend package hierarchy for relative imports ──

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CODEMAP_DIR = _PROJECT_ROOT / "modules" / "codemap"
_BACKEND_DIR = _CODEMAP_DIR / "backend"

# Build package hierarchy so "from .graph import ..." works
_codemap_pkg = types.ModuleType("codemap")
_codemap_pkg.__path__ = [str(_CODEMAP_DIR)]
sys.modules["codemap"] = _codemap_pkg

_backend_pkg = types.ModuleType("codemap.backend")
_backend_pkg.__path__ = [str(_BACKEND_DIR)]
sys.modules["codemap.backend"] = _backend_pkg
_codemap_pkg.backend = _backend_pkg


def _make_package(full_name: str, path: Path, parent: types.ModuleType, attr: str) -> types.ModuleType:
    pkg = types.ModuleType(full_name)
    pkg.__path__ = [str(path)]
    sys.modules[full_name] = pkg
    setattr(parent, attr, pkg)
    return pkg


_graph_pkg = _make_package("codemap.backend.graph", _BACKEND_DIR / "graph", _backend_pkg, "graph")
_locks_pkg = _make_package("codemap.backend.locks", _BACKEND_DIR / "locks", _backend_pkg, "locks")


def _load_module_from_path(full_name: str, file_path: Path, parent: types.ModuleType, attr: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(full_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    setattr(parent, attr, module)
    spec.loader.exec_module(module)
    return module


def _load_backend_module(name: str) -> types.ModuleType:
    """Load a codemap.backend.* module with proper package prefix."""
    full_name = f"codemap.backend.{name}"
    file_path = _BACKEND_DIR / f"{name}.py"
    return _load_module_from_path(full_name, file_path, _backend_pkg, name)


# Load all backend modules
graph_models_module = _load_module_from_path(
    "codemap.backend.graph.graph_models",
    _BACKEND_DIR / "graph" / "graph_models.py",
    _graph_pkg,
    "graph_models",
)
graph_module = _load_module_from_path(
    "codemap.backend.graph.graph",
    _BACKEND_DIR / "graph" / "graph.py",
    _graph_pkg,
    "graph",
)
indexer_module = _load_backend_module("indexer")
boundary_module = _load_backend_module("boundary_engine")
init_db_module = _load_backend_module("init_db")
validation_module = _load_backend_module("validation")
file_lock_module = _load_module_from_path(
    "codemap.backend.locks.file_lock",
    _BACKEND_DIR / "locks" / "file_lock.py",
    _locks_pkg,
    "file_lock",
)

CodeGraph = graph_module.CodeGraph
ImportEdge = graph_module.ImportEdge
CallEdge = graph_module.CallEdge
CapabilityEdge = graph_module.CapabilityEdge
DbTableEdge = graph_module.DbTableEdge
get_graph = graph_module.get_graph

CodeIndexer = indexer_module.CodeIndexer
_scan_files = indexer_module._scan_files
get_indexer = indexer_module.get_indexer


# ── Test helpers ─────────────────────────────────────────────────────────────

def _write_file(base: Path, rel_path: str, content: str) -> None:
    abs_path = base / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")


def _create_mini_project(tmp_path: Path) -> dict:
    """Create a mini project structure with Python/TS/Vue files and a boundary violation."""
    base = tmp_path

    # Framework backend files
    _write_file(base, "backend/app/config.py", """
SETTINGS = {}
def get_settings():
    return SETTINGS
""")

    _write_file(base, "backend/app/database.py", """
from sqlalchemy.ext.asyncio import AsyncSession
def get_db():
    pass
""")

    _write_file(base, "backend/app/services/module_registry.py", """
_CAPABILITIES = {}
def register_capability(module_key, action, handler, **kwargs):
    _CAPABILITIES[f"{module_key}:{action}"] = handler
def call_capability(target_module, action, params, caller):
    pass
""")

    _write_file(base, "backend/app/routers/internal_admin.py", """
def list_all_files():
    return []
""")

    _write_file(base, "backend/app/models/user.py", """
from sqlalchemy import Column, Integer, String
class User:
    __tablename__ = "framework_users"
    id = Column(Integer)
""")

    # Framework frontend files
    _write_file(base, "frontend/src/desktop/window.ts", """
import { ref } from 'vue'
export function openWindow(name: string) {
    return { id: name }
}
""")

    _write_file(base, "frontend/src/shared/api.ts", """
export function fetchApi(path: string) {
    return fetch(path)
}
""")

    # Module A (compliant)
    _write_file(base, "modules/agent/backend/router.py", """
from app.database import get_db
from app.services.module_registry import register_capability, call_capability

async def my_handler(params, caller):
    result = await call_capability("terminal-tools", "exec", params, caller)
    return result

register_capability("agent", "chat", my_handler, description="Chat")
""")

    _write_file(base, "modules/agent/backend/service.py", """
from .router import my_handler

class AgentService:
    def process(self, msg):
        pass
""")

    _write_file(base, "modules/agent/frontend/index.vue", """
<script setup>
import { ref } from 'vue'
import { fetchApi } from '@/shared/api'

const messages = ref([])

async function sendMessage(content: string) {
    const result = await fetchApi('/api/agent/chat')
    platform.modules.call('terminal-tools', 'exec', { command: 'ls' })
}
</script>
<template>
    <div>{{ messages }}</div>
</template>
""")

    # Module B (has boundary violations)
    _write_file(base, "modules/bad_module/backend/router.py", """
import sys
# VIOLATION: importing another module's internal file
from modules.agent.backend.service import AgentService

# VIOLATION: importing framework internal
from app.routers.internal_admin import list_all_files

# VIOLATION: framework table name in string
TABLE = "framework_users"

service = AgentService()
""")

    _write_file(base, "modules/bad_module/backend/models.py", """
from sqlalchemy import Column, Integer, ForeignKey

class BadModel:
    __tablename__ = "bad_module_items"
    id = Column(Integer)
    # VIOLATION: ForeignKey to framework table
    user_id = Column(Integer, ForeignKey("framework_users.id"))
""")

    # Module C (terminal-tools)
    _write_file(base, "modules/terminal-tools/backend/router.py", """
from app.database import get_db
from app.services.module_registry import register_capability

async def exec_cmd(params, caller):
    return {"stdout": "ok"}

register_capability("terminal-tools", "exec", exec_cmd)
register_capability("terminal-tools", "write_file", exec_cmd)
register_capability("terminal-tools", "read_file", exec_cmd)
""")

    # TypeScript file in module
    _write_file(base, "modules/terminal-tools/frontend/index.ts", """
import { ref } from 'vue'
import type { Ref } from 'vue'

export function useTerminal(): Ref<string> {
    const output = ref('')
    return output
}

async function doCall() {
    await platform.modules.call('agent', 'chat', { content: 'hi' })
}
""")

    return {
        "python_files": [
            "backend/app/config.py", "backend/app/database.py",
            "backend/app/services/module_registry.py",
            "backend/app/routers/internal_admin.py",
            "backend/app/models/user.py",
            "modules/agent/backend/router.py",
            "modules/agent/backend/service.py",
            "modules/bad_module/backend/router.py",
            "modules/bad_module/backend/models.py",
            "modules/terminal-tools/backend/router.py",
        ],
        "ts_files": [
            "frontend/src/desktop/window.ts",
            "frontend/src/shared/api.ts",
            "modules/terminal-tools/frontend/index.ts",
        ],
        "vue_files": [
            "modules/agent/frontend/index.vue",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeGraphIsolated:
    """Tests for the graph data structure in isolation."""

    def test_add_file_and_symbol(self):
        graph = CodeGraph()
        graph._ensure_file_node("backend/app/main.py", "framework-backend", None, "python")
        graph.add_symbol("backend/app/main.py::setup", "setup", "function",
                         "backend/app/main.py", 10, 50)

        assert len(graph._files) == 1
        assert len(graph._symbols) == 1
        node = graph._files["backend/app/main.py"]
        assert node.layer == "framework-backend"
        assert len(node.symbols) == 1

    def test_import_edge(self):
        graph = CodeGraph()
        graph._ensure_file_node("a.py", "module", "alpha")
        graph._ensure_file_node("b.py", "module", "beta")
        graph.add_import(ImportEdge(source="a.py", target="b.py",
                                     cross_module=True, line=5))

        result = graph.get_file("a.py")
        assert result is not None
        assert len(result["imports"]) == 1

    def test_clear_file(self):
        graph = CodeGraph()
        graph._ensure_file_node("a.py", "module", "alpha")
        graph._ensure_file_node("b.py", "module", "beta")
        graph.add_import(ImportEdge(source="a.py", target="b.py",
                                     cross_module=True))

        graph.clear_file("a.py")
        assert "a.py" not in graph._files

    def test_stats_initial(self):
        graph = CodeGraph()
        stats = graph.stats()
        assert stats["ready"] is False
        assert stats["file_count"] == 0
        assert stats["index_status"] == "building"
        assert stats["confidence"] == 0

    def test_finish_build_empty_index_is_not_ready(self):
        graph = CodeGraph()
        graph.begin_build()
        graph.finish_build(0)
        stats = graph.stats()
        assert stats["ready"] is False
        assert stats["index_status"] == "unavailable"
        assert stats["index_empty"] is True
        assert stats["build_error"] == "scan found no source files"
        assert stats["confidence"] == 0

    def test_impact_simple(self):
        graph = CodeGraph()
        graph._ensure_file_node("a.py", "module", "alpha")
        graph._ensure_file_node("b.py", "module", "beta")
        graph._ensure_file_node("c.py", "framework-backend", None)
        graph.add_import(ImportEdge(source="a.py", target="b.py"))
        graph.add_import(ImportEdge(source="b.py", target="c.py"))

        result = graph.impact("a.py")
        assert "error" not in result
        forward_files = result["forward_impact"]["files"]
        assert "b.py" in forward_files
        assert "c.py" in forward_files

    def test_impact_missing_file_returns_error(self):
        graph = CodeGraph()
        result = graph.impact("missing.py")
        assert result["error"] == "File not found: missing.py"
        assert result["path"] == "missing.py"

    def test_check_boundary_compliant(self):
        graph = CodeGraph()
        graph._ensure_file_node("modules/ok/backend/r.py", "module", "ok")
        result = graph.check_boundary(path="modules/ok/backend/r.py")
        assert result["compliant"] is True

    def test_check_boundary_missing_target_returns_error(self):
        graph = CodeGraph()
        result = graph.check_boundary()
        assert result["error"] == "Provide path or module_key"

    def test_check_boundary_violation(self):
        graph = CodeGraph()
        graph._ensure_file_node("modules/ok/backend/r.py", "module", "ok")
        graph._ensure_file_node("modules/other/backend/s.py", "module", "other")
        graph.add_import(ImportEdge(
            source="modules/ok/backend/r.py",
            target="modules/other/backend/s.py",
            cross_module=True,
            line=10,
        ))

        result = graph.check_boundary(path="modules/ok/backend/r.py")
        assert result["compliant"] is False
        assert len(result["violations"]) >= 1
        assert any(v["type"] == "cross_module_import" for v in result["violations"])

    def test_framework_public_imports_are_allowed(self):
        graph = CodeGraph()
        graph._ensure_file_node("modules/ok/backend/r.py", "module", "ok")
        public_paths = [
            "backend/app/middleware/auth.py",
            "backend/app/models/user.py",
            "backend/app/models/file.py",
            "backend/app/core/exceptions.py",
            "backend/app/gateway/router.py",
        ]
        for idx, target in enumerate(public_paths, start=1):
            graph._ensure_file_node(target, "framework-backend", None)
            graph.add_import(ImportEdge(
                source="modules/ok/backend/r.py",
                target=target,
                line=idx,
            ))

        result = graph.check_boundary(path="modules/ok/backend/r.py")
        assert result["compliant"] is True
        assert result["violations"] == []

    def test_search(self):
        graph = CodeGraph()
        graph._ensure_file_node("modules/agent/router.py", "module", "agent")
        graph._ensure_file_node("modules/terminal/router.py", "module", "terminal-tools")
        graph.add_symbol("modules/agent/router.py::chat", "chat", "function",
                         "modules/agent/router.py", 42)

        result = graph.search("router")
        assert result["file_match_count"] >= 2

        result2 = graph.search("chat")
        assert result2["symbol_match_count"] >= 1

    def test_module_map(self):
        graph = CodeGraph()
        graph._ensure_file_node("modules/tt/backend/r.py", "module", "terminal-tools")
        graph.add_capability(CapabilityEdge(
            file="modules/tt/backend/r.py", target="terminal-tools:exec",
            kind="register"))
        graph.add_capability(CapabilityEdge(
            file="modules/tt/backend/r.py", target="terminal-tools:read_file",
            kind="register"))

        result = graph.module_map("terminal-tools")
        assert len(result["exposed_capabilities"]) == 2
        assert "terminal-tools:exec" in result["exposed_capabilities"]

    def test_module_map_missing_module_returns_error(self):
        graph = CodeGraph()
        result = graph.module_map("ghost")
        assert result["error"] == "Module not found: ghost"

    def test_reindex_now_reports_missing_callback(self):
        graph = CodeGraph()
        assert graph.reindex_now() is False
        called = {"value": False}

        def _mark_called() -> None:
            called["value"] = True

        graph.set_reindex_callback(_mark_called)
        assert graph.reindex_now() is True
        assert called["value"] is True

    def test_normalize_path_absolute(self):
        """Absolute path should normalize to project-relative."""
        normalize_path = graph_module.normalize_path
        project_root = Path(__file__).resolve().parents[3]
        abs_path = str(project_root / "modules" / "agent" / "backend" / "router.py")
        rel = normalize_path(abs_path)
        assert rel == "modules/agent/backend/router.py", f"Got {rel}"

    def test_normalize_path_relative_cleanup(self):
        """Relative paths with ./ or trailing / should be cleaned."""
        normalize_path = graph_module.normalize_path
        assert normalize_path("./modules/agent/backend/router.py") == "modules/agent/backend/router.py"
        assert normalize_path("modules/agent/backend/router.py/") == "modules/agent/backend/router.py"
        assert normalize_path("modules//agent//backend//router.py") == "modules/agent/backend/router.py"

    def test_query_counting_is_db_persisted(self):
        """query_count is now DB-persisted (codemap_metrics), not on graph.
        The graph no longer has increment_query() / query_count property.
        Router manages query counting via _increment_query_count(db)."""
        graph = CodeGraph()
        graph.begin_build()
        graph.finish_build(1)

        # Stats no longer exposes query_count from graph
        stats = graph.stats()
        assert "query_count" not in stats, \
            "query_count must NOT be in graph.stats() — router fills it from DB"

        # The old methods should not exist
        assert not hasattr(graph, "increment_query"), \
            "increment_query was removed — use router._increment_query_count(db)"
        assert not hasattr(graph, "query_count"), \
            "query_count property was removed — use router._get_query_count(db)"

    def test_ensure_codemap_tables_re_raises_on_failure(self):
        """ensure_codemap_tables must re-raise on failure, not swallow the exception.
        The caller (_ensure_tables_once) depends on this to skip setting
        _tables_ensured = True, which would lock out retry for the process lifetime."""
        import asyncio
        ensure_fn = init_db_module.ensure_codemap_tables

        class FailingDb:
            async def execute(self, *args, **kwargs):
                raise RuntimeError("Simulated DB failure")

            async def rollback(self):
                pass

            async def commit(self):
                pass

        with pytest.raises(RuntimeError, match="Simulated DB failure"):
            asyncio.run(ensure_fn(FailingDb()))

    def test_get_file_failure(self):
        graph = CodeGraph()
        graph.record_file_fail("broken.py", "SyntaxError: invalid syntax")
        graph.record_file_fail("missing_import.py", "ImportError: no module named X")

        assert graph.get_file_failure("broken.py") == "SyntaxError: invalid syntax"
        assert graph.get_file_failure("ok.py") is None

    def test_build_reliability_note_parse_fail(self):
        graph = CodeGraph()
        graph.record_file_fail("broken.py", "SyntaxError: invalid syntax")

        note = graph.build_reliability_note("broken.py")
        assert note is not None
        assert "解析失败" in note
        assert "SyntaxError" in note

    def test_build_reliability_note_feedback(self):
        graph = CodeGraph()
        note = graph.build_reliability_note("complained.py", feedback_count_for_path=3,
                                            latest_feedback_reason="缺失一个导入依赖")
        assert note is not None
        assert "3 次不准" in note
        assert "缺失" in note

    def test_build_reliability_note_no_issues(self):
        graph = CodeGraph()
        # A file with no parse failure, explicit feedback, or staleness (indexed + exists on disk)
        # Use a real file that exists in the project
        graph.record_file_index("backend/app/main.py")
        note = graph.build_reliability_note("backend/app/main.py")
        assert note is None, f"Expected no note for indexed file, got: {note}"

    def test_build_reliability_note_stale(self):
        graph = CodeGraph()
        graph.record_file_index("stale.py")
        note = graph.build_reliability_note("stale.py")
        # File doesn't exist on disk for mtime check, so is_stale returns True
        if note:
            assert "过期" in note

    def test_get_file_absolute_path(self):
        """get_file should accept absolute paths and return same result as relative."""
        graph = CodeGraph()
        graph._ensure_file_node("modules/agent/backend/router.py", "module", "agent", "python")
        graph.add_symbol("modules/agent/backend/router.py::chat", "chat", "function",
                         "modules/agent/backend/router.py", 42)

        # Relative
        rel_result = graph.get_file("modules/agent/backend/router.py")
        assert rel_result is not None

        # Absolute
        project_root = Path(__file__).resolve().parents[3]
        abs_path = str(project_root / "modules" / "agent" / "backend" / "router.py")
        abs_result = graph.get_file(abs_path)
        assert abs_result is not None
        assert abs_result["path"] == rel_result["path"]
        assert abs_result["module_key"] == rel_result["module_key"]


class TestFileLockPersistence:
    """Tests for file-backed locks shared across workers."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "codemap-data"
        monkeypatch.setattr(file_lock_module, "DATA_DIR", data_dir)
        monkeypatch.setattr(file_lock_module, "LOCK_FILE", data_dir / "locks.json")
        monkeypatch.setattr(file_lock_module, "OS_LOCK_FILE", data_dir / "locks.json.lock")

    def test_acquire_lock_persists_to_json(self):
        result = file_lock_module.acquire_lock(
            "modules/codemap/backend/router.py",
            "agent-a",
            ttl=60,
        )
        assert result["success"] is True
        assert file_lock_module.LOCK_FILE.exists()

        stored = file_lock_module._read_locks()
        assert stored["modules/codemap/backend/router.py"]["agent_id"] == "agent-a"

    def test_lock_conflict_and_release(self):
        first = file_lock_module.acquire_lock("modules/codemap/README.md", "agent-a", ttl=60)
        assert first["success"] is True

        conflict = file_lock_module.acquire_lock("modules/codemap/README.md", "agent-b", ttl=60)
        assert conflict["success"] is False
        assert "Already locked" in conflict["error"]

        released = file_lock_module.release_lock("modules/codemap/README.md")
        assert released["success"] is True
        state = file_lock_module.check_lock("modules/codemap/README.md")
        assert state["locked"] is False

    def test_rejects_invalid_lock_inputs(self):
        assert file_lock_module.acquire_lock("", "agent-a")["success"] is False
        assert file_lock_module.acquire_lock("modules/codemap/README.md", "")["success"] is False
        assert file_lock_module.acquire_lock("modules/codemap/README.md", "agent-a", ttl=0)["success"] is False
        outside = file_lock_module.acquire_lock("/tmp/outside-repo-file.py", "agent-a")
        assert outside["success"] is False
        assert outside["error"] == "path must be inside repository root"

    def test_check_lock_invalid_path_fails_closed(self):
        result = file_lock_module.check_lock("/tmp/outside-repo-file.py")
        assert result["success"] is False
        assert result["locked"] is False

    def test_corrupt_lock_store_fails_closed(self):
        file_lock_module.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_lock_module.LOCK_FILE.write_text("{not-json", encoding="utf-8")
        result = file_lock_module.acquire_lock("modules/codemap/README.md", "agent-a", ttl=60)
        assert result["success"] is False
        assert "corrupt" in result["error"]
        assert file_lock_module.LOCK_FILE.read_text(encoding="utf-8") == "{not-json"


class TestInputValidation:
    """Tests for public input validation shared by HTTP and capabilities."""

    def test_feedback_requires_non_empty_path_and_type(self):
        with pytest.raises(ValueError, match="path is required"):
            validation_module.validate_feedback_fields("", "impact")
        with pytest.raises(ValueError, match="query_type is required"):
            validation_module.validate_feedback_fields("modules/codemap/README.md", "")

    def test_feedback_rejects_paths_outside_repo(self):
        with pytest.raises(ValueError, match="inside repository root"):
            validation_module.validate_feedback_fields("../../outside.py", "impact")
        with pytest.raises(ValueError, match="inside repository root"):
            validation_module.validate_feedback_fields("/tmp/outside.py", "impact")

    def test_feedback_normalizes_valid_path(self):
        path, query_type = validation_module.validate_feedback_fields(
            "./modules//codemap/README.md/",
            " verification ",
        )
        assert path == "modules/codemap/README.md"
        assert query_type == "verification"


class TestIndexerFullBuild:
    """Tests that build a complete mini index from a temporary project."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        self.tmp = tmp_path
        self.fixture_files = _create_mini_project(tmp_path)

        # Monkey-patch the indexer to use tmp_path
        monkeypatch.setattr(indexer_module, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(indexer_module, "_SCAN_ROOTS",
                            ["backend/app", "frontend/src", "modules"])

        self.graph = CodeGraph()
        self.indexer = CodeIndexer(graph=self.graph)
        self.indexer.build_full()

    def test_scan_finds_all_files(self):
        files = _scan_files()
        expected = (len(self.fixture_files["python_files"]) +
                    len(self.fixture_files["ts_files"]) +
                    len(self.fixture_files["vue_files"]))
        assert len(files) == expected, f"Expected {expected} files, got {len(files)}"

    def test_build_completes(self):
        assert self.graph.ready is True
        stats = self.graph.stats()
        assert stats["file_count"] > 0

    def test_parse_failure_is_recorded_and_not_indexed_as_success(self):
        broken = self.tmp / "modules" / "agent" / "backend" / "broken.py"
        broken.write_text("def broken(:\n", encoding="utf-8")
        self.indexer.update_file("modules/agent/backend/broken.py")
        stats = self.graph.stats()
        assert self.graph.get_file("modules/agent/backend/broken.py") is None
        assert stats["parse_fail_count"] >= 1
        assert self.graph.get_file_failure("modules/agent/backend/broken.py")

    def test_get_file_python(self):
        result = self.graph.get_file("modules/agent/backend/router.py")
        assert result is not None
        assert result["layer"] == "module"
        assert result["module_key"] == "agent"
        assert result["language"] == "python"
        assert len(result["imports"]) >= 1
        assert len(result["capabilities"]) >= 1

    def test_get_file_vue(self):
        result = self.graph.get_file("modules/agent/frontend/index.vue")
        assert result is not None
        assert result["layer"] == "module"
        assert result["language"] == "vue"
        caps = [c for c in result.get("capabilities", []) if c["kind"] == "call"]
        assert len(caps) >= 1
        assert any("terminal-tools" in c["target"] for c in caps)

    def test_impact_framework_file(self):
        result = self.graph.impact("backend/app/database.py")
        assert "error" not in result
        reverse_files = result["reverse_impact"]["files"]
        assert len(reverse_files) >= 1

    def test_impact_module_file(self):
        result = self.graph.impact("modules/agent/backend/router.py")
        assert "error" not in result
        forward = result["forward_impact"]["files"]
        assert len(forward) >= 1

    def test_check_boundary_violations_detected(self):
        result = self.graph.check_boundary(
            path="modules/bad_module/backend/router.py")
        assert result["compliant"] is False
        violation_types = [v["type"] for v in result["violations"]]
        assert "cross_module_import" in violation_types
        assert "framework_internal_import" in violation_types

    def test_check_boundary_compliant_module(self):
        result = self.graph.check_boundary(module_key="agent")
        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    def test_module_map_terminal_tools(self):
        result = self.graph.module_map("terminal-tools")
        assert len(result["exposed_capabilities"]) >= 3
        capabilities = result["exposed_capabilities"]
        assert any("terminal-tools:exec" in c for c in capabilities)
        assert any("terminal-tools:write_file" in c for c in capabilities)
        assert any("terminal-tools:read_file" in c for c in capabilities)
        assert result["boundary"]["compliant"] is True

    def test_module_map_agent(self):
        result = self.graph.module_map("agent")
        assert "agent:chat" in result["exposed_capabilities"]
        consumed = result["consumed_capabilities"]
        assert any("terminal-tools" in c for c in consumed)

    def test_search_finds_files(self):
        result = self.graph.search("router")
        assert result["file_match_count"] >= 3
        file_paths = [m["path"] for m in result["file_matches"]]
        assert any("router.py" in p for p in file_paths)

    def test_search_finds_symbols(self):
        result = self.graph.search("get_db")
        assert result["symbol_match_count"] >= 1

    def test_stats(self):
        stats = self.graph.stats()
        assert stats["ready"] is True
        assert stats["index_scope"] == "process-local"
        assert stats["file_count"] > 0
        assert stats["build_time_seconds"] >= 0

    def test_rebuild_does_not_duplicate_edges(self):
        before = self.graph.stats()
        self.indexer.build_full()
        after = self.graph.stats()

        for key in ("file_count", "symbol_count", "import_edges", "capability_edges", "db_table_edges"):
            assert after[key] == before[key], f"{key} changed after rebuild: {before[key]} -> {after[key]}"

    def test_incremental_update(self):
        new_file = self.tmp / "modules" / "agent" / "backend" / "utils.py"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("""
from app.database import get_db

def helper():
    return get_db()
""")

        self.indexer.update_file("modules/agent/backend/utils.py")
        assert "modules/agent/backend/utils.py" in self.graph._files
        result = self.graph.get_file("modules/agent/backend/utils.py")
        assert result is not None
        assert len(result["imports"]) >= 1

    def test_boundary_violation_after_fix(self):
        fixed_content = """
from app.database import get_db
# import removed
""".strip()
        bad_file = self.tmp / "modules" / "bad_module" / "backend" / "router.py"
        bad_file.write_text(fixed_content)

        self.indexer.update_file("modules/bad_module/backend/router.py")
        result = self.graph.check_boundary(
            path="modules/bad_module/backend/router.py")
        violation_types = [v["type"] for v in result["violations"]]
        assert "cross_module_import" not in violation_types
        assert "framework_internal_import" not in violation_types

    def test_plain_strings_are_not_table_edges(self):
        sample = self.tmp / "modules" / "codemap" / "backend" / "sample.py"
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_text("""
RULE = "framework_table_access"
EXAMPLE = "agent_conversations"
def explain():
    return "framework_internal_import"
""")

        self.indexer.update_file("modules/codemap/backend/sample.py")
        info = self.graph.get_file("modules/codemap/backend/sample.py")
        assert info is not None
        assert info["db_tables"] == []

    def test_sql_and_orm_contexts_are_table_edges(self):
        sample = self.tmp / "modules" / "agent" / "backend" / "sql_sample.py"
        sample.write_text("""
from sqlalchemy import ForeignKey, text

class Conversation:
    __tablename__ = "agent_conversations"
    owner_id = ForeignKey("framework_user_accounts.id")

async def load(db):
    await db.execute(text("SELECT id FROM agent_messages WHERE conversation_id = :cid"))
""")

        self.indexer.update_file("modules/agent/backend/sql_sample.py")
        info = self.graph.get_file("modules/agent/backend/sql_sample.py")
        assert info is not None
        tables = {edge["table_name"] for edge in info["db_tables"]}
        assert "agent_conversations" in tables
        assert "framework_user_accounts" in tables
        assert "agent_messages" in tables


class TestRealProjectIntegration:
    """Integration tests against the real project (not temp dir)."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        # Use real project root — indexer already uses Path(__file__).resolve().parents[3]
        # which points to the real project root from within modules/codemap/tests/
        self.graph = CodeGraph()
        self.indexer = CodeIndexer(graph=self.graph)

        # Collect parse errors via a hook
        self.parse_errors: list[str] = []
        original_parse_file = indexer_module._parse_file

        def _tracking_parse_file(file_path, graph):
            try:
                original_parse_file(file_path, graph)
            except Exception as exc:
                self.parse_errors.append(f"{file_path}: {exc}")

        monkeypatch.setattr(indexer_module, "_parse_file", _tracking_parse_file)
        self.indexer.build_full()

    def test_zero_parse_errors(self):
        """build_full() must produce 0 Parse errors."""
        if self.parse_errors:
            print("\nParse errors found:")
            for e in self.parse_errors:
                print(f"  {e}")
        assert len(self.parse_errors) == 0, (
            f"Expected 0 parse errors, got {len(self.parse_errors)}"
        )

    def test_key_frontend_files_not_empty(self):
        """frontend/src/main.ts must have imports."""
        info = self.graph.get_file("frontend/src/main.ts")
        assert info is not None, "main.ts not found in index"
        assert len(info["imports"]) >= 1, (
            f"main.ts has {len(info['imports'])} imports, expected >= 1"
        )

    def test_stats_post_fix(self):
        """Verify post-fix stats are within expected ranges."""
        stats = self.graph.stats()
        assert stats["ready"] is True
        assert stats["file_count"] >= 280
        assert stats["symbol_count"] >= 1000
        assert stats["import_edges"] >= 600, (
            f"import_edges={stats['import_edges']}, expected >= 600 after fix"
        )

    def test_ts_vue_coverage(self):
        """≥95% of TS/Vue files with project-internal imports resolve edges."""
        try:
            import tree_sitter_typescript as tstypescript
            from tree_sitter import Language, Parser
        except ImportError:
            pytest.skip("tree-sitter-typescript not available")

        ts_lang = Language(tstypescript.language_typescript())
        parser = Parser(ts_lang)
        _VUE_SCRIPT_RE = __import__("re").compile(
            r"<script\b[^>]*>(.*?)</script>", __import__("re").DOTALL)

        def _get_internal_imports(source: str) -> list[str]:
            """Extract ./, ../, @/ import specifiers via tree-sitter."""
            specs = []
            tree = parser.parse(source.encode())
            def walk(node):
                if node.type == "import_statement":
                    src_node = node.child_by_field_name("source")
                    if src_node and src_node.type == "string":
                        val = source[src_node.start_byte:src_node.end_byte]
                        if len(val) >= 2:
                            inner = val[1:-1]
                            if inner.startswith(".") or (
                            inner.startswith("@") and inner.startswith("@/")):
                                specs.append(inner)
                for c in node.children:
                    walk(c)
            walk(tree.root_node)
            return specs

        has_internal = 0
        has_internal_and_resolved = 0
        unresolved: list[tuple[str, list[str]]] = []

        for path, node in self.graph._files.items():
            if node.language not in ("typescript", "vue"):
                continue
            abs_path = _PROJECT_ROOT / path
            if not abs_path.exists():
                continue
            source = abs_path.read_text(encoding="utf-8", errors="ignore")

            if node.language == "vue":
                scripts = _VUE_SCRIPT_RE.findall(source)
                imports = []
                for s in scripts:
                    if s.strip():
                        imports.extend(_get_internal_imports(s))
            else:
                imports = _get_internal_imports(source)

            if imports:
                has_internal += 1
                edges = self.graph._imports.get(path, [])
                if len(edges) >= 1:
                    has_internal_and_resolved += 1
                else:
                    unresolved.append((path, imports))

        print(f"\nTS/Vue files with internal imports (./ ../ @/): {has_internal}")
        print(f"With >=1 resolved import edge: {has_internal_and_resolved}")
        if has_internal > 0:
            pct = has_internal_and_resolved / has_internal * 100
            print(f"Coverage: {pct:.1f}%")
            if unresolved:
                print(f"Still unresolved ({len(unresolved)}):")
                for p, imps in unresolved[:5]:
                    print(f"  {p}: {imps[:3]}")
            assert pct >= 95.0, f"Coverage {pct:.1f}% < 95%"

    def test_python_no_regression(self):
        """Python-side stats should not regress."""
        python_files = sum(
            1 for n in self.graph._files.values() if n.language == "python"
        )
        assert python_files >= 100, f"Only {python_files} Python files"
        # __init__.py files are legit empty; check non-init files
        non_init_empty = [
            p for p, n in self.graph._files.items()
            if n.language == "python" and len(n.symbols) == 0
            and len(self.graph._imports.get(p, [])) == 0
            and not p.endswith("__init__.py")
        ]
        assert len(non_init_empty) < 5, (
            f"Empty non-init Python files: {non_init_empty}"
        )
