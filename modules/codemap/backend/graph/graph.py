"""In-memory code graph with bidirectional adjacency for fast impact analysis.

Data model:

FileNode:  path, layer, module_key, language, symbols
SymbolNode: id, name, kind, file, start_line, end_line

Edges (stored in adjacency lists, each edge has metadata):
  import:           source_file -> target_file  (cross_module: bool, compliant: bool|None)
  call:             source_symbol_id -> target_symbol_id
  capability_register: file -> "module:action"
  capability_call:     file -> "module:action"
  db_table:            file -> table_name

Thread safety: RLock — queries read current snapshot; writes acquire lock.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

from .graph_models import (
    CallEdge,
    CapabilityEdge,
    DbTableEdge,
    FileNode,
    ImportEdge,
)

logger = logging.getLogger("v2.codemap").getChild("graph")
# Project root — graph.py lives in modules/codemap/backend/graph/graph.py
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

def normalize_path(path: str) -> str:
    """Convert an input path to a project-relative path suitable for index lookup.

    - Absolute paths → strip project root to get relative path
    - Relative paths → clean . / .. / trailing slash / double slash
    - Uses os.path.normpath for cross-platform consistency
    """
    if not path:
        return path

    # If it's an absolute path, try to make it relative to project root
    p = Path(path)
    if p.is_absolute():
        try:
            rel = p.resolve().relative_to(_PROJECT_ROOT.resolve())
            return str(rel)
        except ValueError:
            # Not under project root — try resolving anyway
            pass

    # Clean relative path: normalize, strip leading ./, trailing /
    cleaned = os.path.normpath(path).replace("\\", "/")
    # Remove leading ./
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    # Remove trailing /
    cleaned = cleaned.rstrip("/")
    return cleaned

# ── Graph ──────────────────────────────────────────────────────────────────

class CodeGraph:
    """Thread-safe in-memory code relationship graph."""

    def __init__(self):
        self._lock = threading.RLock()

        # Nodes
        self._files: dict[str, FileNode] = {}           # path -> FileNode
        self._symbols: dict[str, dict] = {}             # symbol_id -> {name, kind, file, start_line, end_line}

        # Forward adjacency
        self._imports: dict[str, list[ImportEdge]] = {}          # source -> [ImportEdge]
        self._calls: dict[str, list[CallEdge]] = {}              # source_symbol_id -> [CallEdge]
        self._capabilities: dict[str, list[CapabilityEdge]] = {} # file -> [CapabilityEdge]
        self._db_tables: dict[str, list[DbTableEdge]] = {}       # file -> [DbTableEdge]

        # Reverse adjacency (for impact: "who depends on me")
        self._rev_imports: dict[str, list[ImportEdge]] = {}      # target -> [ImportEdge]
        self._rev_calls: dict[str, list[CallEdge]] = {}

        # Stats
        self._build_start: float = 0.0
        self._build_end: float = 0.0
        self._ready: bool = False
        self._file_count_at_build: int = 0
        self._file_mtimes: dict[str, float] = {}
        self._failed_files: list[dict] = []
        self._total_files_scanned: int = 0
        self._build_error: str | None = None

        # ── Rebuild trigger ──────────────────────────────────────────
        self._reindex_callback: callable | None = None

    # ── Write helpers ──────────────────────────────────────────────────

    def _ensure_file_node(self, path: str, layer: str = "", module_key: str | None = None,
                          language: str = "") -> FileNode:
        if path not in self._files:
            self._files[path] = FileNode(path=path, layer=layer, module_key=module_key, language=language)
        else:
            node = self._files[path]
            if layer:
                node.layer = layer
            if module_key:
                node.module_key = module_key
            if language:
                node.language = language
        return self._files[path]

    def add_symbol(self, symbol_id: str, name: str, kind: str, file: str,
                   start_line: int = 0, end_line: int = 0) -> None:
        self._symbols[symbol_id] = {
            "name": name, "kind": kind, "file": file,
            "start_line": start_line, "end_line": end_line,
        }
        if file in self._files:
            self._files[file].symbols.append({
                "id": symbol_id, "name": name, "kind": kind,
                "start_line": start_line, "end_line": end_line,
            })

    def add_import(self, edge: ImportEdge) -> None:
        self._imports.setdefault(edge.source, []).append(edge)
        self._rev_imports.setdefault(edge.target, []).append(edge)

    def add_call(self, edge: CallEdge) -> None:
        self._calls.setdefault(edge.source_symbol_id, []).append(edge)
        self._rev_calls.setdefault(edge.target_symbol_id, []).append(edge)

    def add_capability(self, edge: CapabilityEdge) -> None:
        self._capabilities.setdefault(edge.file, []).append(edge)

    def add_db_table(self, edge: DbTableEdge) -> None:
        existing = self._db_tables.setdefault(edge.file, [])
        if any(e.table_name == edge.table_name and e.line == edge.line for e in existing):
            return
        existing.append(edge)

    # ── Bulk operations ────────────────────────────────────────────────

    def clear_file(self, path: str) -> None:
        """Remove a file and all its edges from the graph."""
        with self._lock:
            # Remove reverse import edges pointing to this file
            for rev_edge in self._rev_imports.pop(path, []):
                src_list = self._imports.get(rev_edge.source)
                if src_list:
                    src_list[:] = [e for e in src_list if e.target != path]

            # Remove forward import edges from this file
            for fwd_edge in self._imports.pop(path, []):
                rev_list = self._rev_imports.get(fwd_edge.target)
                if rev_list:
                    rev_list[:] = [e for e in rev_list if e.source != path]

            # Remove capability edges
            self._capabilities.pop(path, None)

            # Remove db table edges
            self._db_tables.pop(path, None)

            # Remove symbols belonging to this file
            removed_ids = [sid for sid, s in self._symbols.items() if s["file"] == path]

            # Remove call edges for removed symbols
            for sid in removed_ids:
                for ce in self._calls.pop(sid, []):
                    rev_list = self._rev_calls.get(ce.target_symbol_id)
                    if rev_list:
                        rev_list[:] = [e for e in rev_list if e.source_symbol_id != sid]
                self._rev_calls.pop(sid, None)

            for sid in removed_ids:
                self._symbols.pop(sid, None)

            # Remove file node
            self._files.pop(path, None)
            # Remove mtime tracking
            self._file_mtimes.pop(path, None)

    def begin_build(self) -> None:
        with self._lock:
            self._ready = False
            self._build_start = time.time()
            self._files.clear()
            self._symbols.clear()
            self._imports.clear()
            self._calls.clear()
            self._capabilities.clear()
            self._db_tables.clear()
            self._rev_imports.clear()
            self._rev_calls.clear()
            self._file_mtimes.clear()
            self._failed_files.clear()
            self._total_files_scanned = 0
            self._build_error = None

    def finish_build(self, file_count: int) -> None:
        with self._lock:
            self._build_end = time.time()
            self._file_count_at_build = file_count
            self._total_files_scanned = file_count
            if file_count <= 0:
                self._build_error = "scan found no source files"
            elif len(self._files) <= 0:
                self._build_error = "no files parsed successfully"
            else:
                self._build_error = None
            self._ready = self._build_error is None

    @property
    def ready(self) -> bool:
        return self._ready

    # ── Index tracking ────────────────────────────────────────────────

    def record_file_index(self, file_path: str) -> None:
        """Record file's mtime at index time (for stale detection)."""
        abs_path = _PROJECT_ROOT / file_path
        try:
            mtime = abs_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        self._file_mtimes[file_path] = mtime

    def record_file_fail(self, file_path: str, error: str) -> None:
        """Record a file that failed to parse."""
        self._failed_files.append({"path": file_path, "error": str(error)[:200]})

    def is_file_stale(self, file_path: str) -> bool:
        """Check if a file's disk mtime is newer than its index time."""
        indexed_mtime = self._file_mtimes.get(file_path)
        if indexed_mtime is None:
            return True
        try:
            disk_mtime = (_PROJECT_ROOT / file_path).stat().st_mtime
        except OSError:
            return True
        return disk_mtime > indexed_mtime

    def set_reindex_callback(self, cb: callable | None) -> None:
        """Set a callback to trigger a full rebuild from outside."""
        self._reindex_callback = cb

    def get_file_failure(self, file_path: str) -> str | None:
        """Return the parse error message for a file if it failed to parse, else None."""
        for entry in self._failed_files:
            if entry["path"] == file_path:
                return entry["error"]
        return None

    # ── Reliability note ──────────────────────────────────────────────

    def build_reliability_note(
        self,
        path: str,
        feedback_count_for_path: int = 0,
        latest_feedback_reason: str = "",
    ) -> str | None:
        """Build a human-readable note about why this file's data may be unreliable."""
        notes: list[str] = []

        fail_reason = self.get_file_failure(path)
        if fail_reason:
            notes.append(f"该文件解析失败: {fail_reason}，依赖可能不全")

        if self.is_file_stale(path):
            notes.append("索引可能过期，建议实读或 rebuild")

        if feedback_count_for_path > 0:
            notes.append(f"该文件曾被反馈 {feedback_count_for_path} 次不准，最近原因: {latest_feedback_reason}")

        return "；".join(notes) if notes else None

    def reindex_now(self) -> bool:
        """Trigger a full rebuild via the registered callback."""
        if self._reindex_callback:
            self._reindex_callback()
            return True
        return False

    # ── Query: get_file ────────────────────────────────────────────────

    def get_file(self, path: str) -> dict | None:
        """Return full info for a file."""
        path = normalize_path(path)
        with self._lock:
            node = self._files.get(path)
            if not node:
                return None
            info = node.to_dict()
            info["imports"] = [e.to_dict() for e in self._imports.get(path, [])]
            info["imported_by"] = [e.to_dict() for e in self._rev_imports.get(path, [])]
            info["capabilities"] = [e.to_dict() for e in self._capabilities.get(path, [])]
            info["db_tables"] = [e.to_dict() for e in self._db_tables.get(path, [])]
            info["stale"] = self.is_file_stale(path)
            return info

    # ── Query: impact (transitive closure) ─────────────────────────────

    def impact(self, path: str, symbol_name: str | None = None) -> dict:
        """Return forward + reverse transitive impact for a file (optionally scoped to a symbol)."""
        path = normalize_path(path)
        with self._lock:
            node = self._files.get(path)
            if not node:
                return {"error": f"File not found: {path}", "path": path}

            # Collect the set of symbol IDs to start from
            start_symbols: list[str] = []
            if symbol_name:
                start_symbols = [sid for sid, s in self._symbols.items()
                                 if s["file"] == path and s["name"] == symbol_name]
            else:
                start_symbols = [sid for sid, s in self._symbols.items() if s["file"] == path]

            # Forward transitive closure (I depend on them)
            forward_files: set[str] = set()
            forward_modules: set[str] = set()
            forward_capabilities: list[str] = []
            visited_imports: set[str] = set()
            queue: deque[str] = deque([path])

            while queue:
                cur = queue.popleft()
                if cur in visited_imports:
                    continue
                visited_imports.add(cur)
                for edge in self._imports.get(cur, []):
                    if edge.target not in forward_files:
                        forward_files.add(edge.target)
                        queue.append(edge.target)
                        target_node = self._files.get(edge.target)
                        if target_node and target_node.module_key:
                            forward_modules.add(target_node.module_key)
                for cap_edge in self._capabilities.get(cur, []):
                    if cap_edge.kind == "call":
                        forward_capabilities.append(cap_edge.target)

            # Reverse transitive closure (who depends on me)
            reverse_files: set[str] = set()
            reverse_modules: set[str] = set()
            visited_rev: set[str] = set()
            queue = deque([path])
            while queue:
                cur = queue.popleft()
                if cur in visited_rev:
                    continue
                visited_rev.add(cur)
                for edge in self._rev_imports.get(cur, []):
                    if edge.source not in reverse_files:
                        reverse_files.add(edge.source)
                        queue.append(edge.source)
                        src_node = self._files.get(edge.source)
                        if src_node and src_node.module_key:
                            reverse_modules.add(src_node.module_key)

            # Risk level assessment
            if len(reverse_modules) > 3 or len(forward_modules) > 3:
                risk = "high"
            elif len(reverse_modules) > 1 or len(forward_modules) > 1:
                risk = "medium"
            else:
                risk = "low"

            return {
                "path": path,
                "symbol": symbol_name,
                "symbol_ids": start_symbols,
                "stale": self.is_file_stale(path),
                "forward_impact": {
                    "files": sorted(forward_files),
                    "file_count": len(forward_files),
                    "modules": sorted(forward_modules),
                    "capabilities": sorted(forward_capabilities),
                },
                "reverse_impact": {
                    "files": sorted(reverse_files),
                    "file_count": len(reverse_files),
                    "modules": sorted(reverse_modules),
                },
                "risk": risk,
            }

    # ── Query: check_boundary ──────────────────────────────────────────

    def check_boundary(self, path: str | None = None, module_key: str | None = None) -> dict:
        """Check boundary compliance for a file or an entire module.

        Returns violations of AGENTS.md rules 17-20:
        - Module file importing another module's internal file
        - Module file importing framework internals (frontend/src/*, backend/app/services/*)
        - Module accessing framework_* tables or other module tables
        """
        if path:
            path = normalize_path(path)
        with self._lock:
            if path:
                return self._check_file_boundary(path)
            if module_key:
                return self._check_module_boundary(module_key)
            return {"error": "Provide path or module_key"}

    def _check_file_boundary(self, path: str) -> dict:
        from ..boundary_engine import is_framework_internal

        node = self._files.get(path)
        if not node:
            return {"error": f"File not found: {path}", "path": path}

        violations: list[dict] = []

        # Rule: module file importing other module internals
        if node.layer == "module":
            source_module = node.module_key
            for edge in self._imports.get(path, []):
                target_node = self._files.get(edge.target)
                if not target_node:
                    continue
                # Another module's internal file
                if target_node.layer == "module" and target_node.module_key != source_module:
                    violations.append({
                        "type": "cross_module_import",
                        "rule": "铁律17: 模块间禁止互相import",
                        "source": path,
                        "target": edge.target,
                        "target_module": target_node.module_key,
                        "line": edge.line,
                        "imported_name": edge.imported_name,
                    })
                # Framework internal (only if actually internal, not public)
                if target_node.layer.startswith("framework-"):
                    if is_framework_internal(edge.target):
                        violations.append({
                            "type": "framework_internal_import",
                            "rule": "铁律19: 模块禁止import框架内部文件",
                            "source": path,
                            "target": edge.target,
                            "target_layer": target_node.layer,
                            "line": edge.line,
                            "imported_name": edge.imported_name,
                        })

        # Rule: module accessing framework_* or other module tables
        if node.layer == "module" and node.module_key:
            for db_edge in self._db_tables.get(path, []):
                table = db_edge.table_name.lower()
                if table.startswith("framework_"):
                    violations.append({
                        "type": "framework_table_access",
                        "rule": "铁律17: 模块禁止操作framework_*表",
                        "source": path,
                        "table": db_edge.table_name,
                        "line": db_edge.line,
                    })
                elif "_" in table:
                    # Check if table prefix matches a different module key
                    prefix = table.split("_", 1)[0]
                    if prefix != node.module_key and prefix not in ("t_", "v_", "sys_"):
                        # Could be another module's table
                        for other_node in self._files.values():
                            if other_node.module_key == prefix:
                                violations.append({
                                    "type": "cross_module_table_access",
                                    "rule": "铁律17: 模块禁止操作其他模块表",
                                    "source": path,
                                    "table": db_edge.table_name,
                                    "owner_module": prefix,
                                    "line": db_edge.line,
                                })
                                break

        return {
            "target": path,
            "module_key": node.module_key,
            "layer": node.layer,
            "violations": violations,
            "compliant": len(violations) == 0,
        }

    def _check_module_boundary(self, module_key: str) -> dict:
        module_files = [p for p, n in self._files.items()
                        if n.module_key == module_key]
        all_violations: list[dict] = []
        for fpath in module_files:
            result = self._check_file_boundary(fpath)
            if result.get("violations"):
                all_violations.extend(result["violations"])

        return {
            "module_key": module_key,
            "file_count": len(module_files),
            "files": sorted(module_files),
            "violations": all_violations,
            "compliant": len(all_violations) == 0,
        }

    # ── Query: module_map ──────────────────────────────────────────────

    def module_map(self, module_key: str) -> dict:
        """Return module-level overview: capabilities exposed, capabilities consumed, boundary health."""
        module_key = (module_key or "").strip()
        if not module_key:
            return {"error": "module_key is required"}
        with self._lock:
            module_files = [p for p, n in self._files.items()
                            if n.module_key == module_key]
            if not module_files:
                return {"error": f"Module not found: {module_key}", "module_key": module_key}

            # Capabilities registered by this module
            exposed: list[str] = []
            # Capabilities called by this module (from other modules)
            consumed: list[str] = []
            # Modules this module depends on
            depends_on: set[str] = set()
            # Modules that depend on this module
            depended_by: set[str] = set()

            for fpath in module_files:
                for cap in self._capabilities.get(fpath, []):
                    if cap.kind == "register":
                        exposed.append(cap.target)
                    elif cap.kind == "call":
                        consumed.append(cap.target)
                        # Extract target module from "module:action"
                        if ":" in cap.target:
                            target_mod = cap.target.split(":", 1)[0]
                            if target_mod != module_key:
                                depends_on.add(target_mod)

                for imp in self._imports.get(fpath, []):
                    target_node = self._files.get(imp.target)
                    if target_node and target_node.module_key:
                        tmod = target_node.module_key
                        if tmod != module_key:
                            depends_on.add(tmod)

            # Reverse: who imports this module's files
            for fpath, node in self._files.items():
                if node.module_key == module_key:
                    continue
                for imp in self._imports.get(fpath, []):
                    target_node = self._files.get(imp.target)
                    if target_node and target_node.module_key == module_key:
                        depended_by.add(node.module_key or "framework")
                        break

            # Boundary health
            boundary = self._check_module_boundary(module_key)

            return {
                "module_key": module_key,
                "file_count": len(module_files),
                "layer": self._files[module_files[0]].layer if module_files else "unknown",
                "exposed_capabilities": sorted(set(exposed)),
                "consumed_capabilities": sorted(set(consumed)),
                "depends_on_modules": sorted(depends_on),
                "depended_by_modules": sorted(depended_by),
                "boundary": {
                    "compliant": boundary["compliant"],
                    "violation_count": len(boundary["violations"]),
                    "violations": boundary["violations"],
                },
            }

    # ── Query: search ──────────────────────────────────────────────────

    def search(self, keyword: str) -> dict:
        """Fuzzy search files and symbols by keyword."""
        kw = keyword.lower()
        with self._lock:
            matched_files: list[dict] = []
            for path, node in self._files.items():
                if kw in path.lower():
                    matched_files.append({
                        "path": path,
                        "layer": node.layer,
                        "module_key": node.module_key,
                        "language": node.language,
                    })
            matched_symbols: list[dict] = []
            for sid, sym in self._symbols.items():
                if kw in sym["name"].lower():
                    matched_symbols.append({
                        "id": sid,
                        "name": sym["name"],
                        "kind": sym["kind"],
                        "file": sym["file"],
                        "line": sym["start_line"],
                    })
            return {
                "keyword": keyword,
                "file_matches": matched_files[:50],
                "file_match_count": len(matched_files),
                "symbol_matches": matched_symbols[:50],
                "symbol_match_count": len(matched_symbols),
            }

    # ── Query: stats ───────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            build_time = (self._build_end - self._build_start) if self._build_end > 0 else 0
            success_count = self._total_files_scanned - len(self._failed_files)
            fail_count = len(self._failed_files)
            parse_rate = (success_count / self._total_files_scanned * 100) if self._total_files_scanned > 0 else 0.0
            freshness_hours = (time.time() - self._build_end) / 3600 if self._build_end > 0 else -1
            ready_score = 50 if self._ready else 0
            freshness_score = max(0, 25 - int(freshness_hours)) if freshness_hours >= 0 else 0
            freshness_score = max(0, min(25, freshness_score))
            parse_score = min(25, int(parse_rate * 0.25))
            confidence = 0 if self._build_error or not self._ready else ready_score + freshness_score + parse_score
            confidence = max(0, min(100, confidence))
            if self._build_error:
                index_status = "unavailable"
            elif self._ready:
                index_status = "ready"
            else:
                index_status = "building"
            return {
                "ready": self._ready,
                "index_status": index_status,
                "index_scope": "process-local",
                "index_empty": len(self._files) == 0,
                "build_error": self._build_error,
                "file_count": len(self._files),
                "file_count_at_build": self._file_count_at_build,
                "symbol_count": len(self._symbols),
                "import_edges": sum(len(v) for v in self._imports.values()),
                "call_edges": sum(len(v) for v in self._calls.values()),
                "capability_edges": sum(len(v) for v in self._capabilities.values()),
                "db_table_edges": sum(len(v) for v in self._db_tables.values()),
                "build_time_seconds": round(build_time, 3),
                "last_build_time": time.strftime("%Y-%m-%d %H:%M:%S",
                                                 time.localtime(self._build_end)) if self._build_end else None,
                "parse_success_count": success_count,
                "parse_fail_count": fail_count,
                "failed_files": self._failed_files[:50],
                "freshness_hours": round(freshness_hours, 1) if freshness_hours >= 0 else None,
                "confidence": confidence,
                "empirical_accuracy": None,     # filled by router from DB feedback
                "feedback_count": None,          # filled by router from DB feedback
                "recent_complaints": [],          # filled by router from DB feedback
            }

# Singleton instance
_graph_instance: CodeGraph | None = None

def get_graph() -> CodeGraph:
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = CodeGraph()
    return _graph_instance
