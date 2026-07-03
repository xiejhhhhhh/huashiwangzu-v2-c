"""Code indexer: file scanner + multi-language parser + graph builder.

Supports:
  - Python:      stdlib `ast` (precise)
  - TypeScript:  tree-sitter AST (tree-sitter + tree-sitter-typescript)
  - Vue:         extract <script> blocks, then TS parse

Scans three roots: backend/app, frontend/src, modules/*
Excludes: node_modules, .venv, dist, __pycache__, .git
"""

from __future__ import annotations

import ast
import logging
import os
import re
import threading
from pathlib import Path

from .graph.graph import (
    CallEdge,
    CapabilityEdge,
    CodeGraph,
    DbTableEdge,
    ImportEdge,
    get_graph,
)

logger = logging.getLogger("v2.codemap").getChild("indexer")

# ── Project root detection ─────────────────────────────────────────────────
# This file lives in modules/codemap/backend/indexer.py
# Project root is 3 levels up: ../../../ -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ── Scan roots (relative to project root) ───────────────────────────────────
_SCAN_ROOTS = ["backend/app", "frontend/src", "modules"]

# ── Public aliases (used by watcher.py) ──────────────────────────────────────
PROJECT_ROOT = _PROJECT_ROOT
SCAN_ROOTS = _SCAN_ROOTS

# ── Exclude patterns ────────────────────────────────────────────────────────
_EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "dist", "__pycache__", ".git",
    ".idea", ".vscode", ".opencode", "data", "sandbox", "tests",
    "_废弃", "脚本", "deploy",
}

_EXCLUDE_PATH_PARTS = {
    "node_modules", ".venv", "venv", "dist", "__pycache__", ".git",
}

# ── File extensions to scan ─────────────────────────────────────────────────
_PY_EXT = {".py"}
_TS_EXT = {".ts", ".tsx"}
_VUE_EXT = {".vue"}
_ALL_EXT = _PY_EXT | _TS_EXT | _VUE_EXT

# ── Regex patterns for TypeScript/Vue parsing ───────────────────────────────

# Import patterns
_RE_IMPORT_NAMED = re.compile(
    r"""import\s*\{[^}]*\}\s*from\s*['"]([^'"]+)['"]""")
_RE_IMPORT_DEFAULT = re.compile(
    r"""import\s+(\w+)\s+from\s*['"]([^'"]+)['"]""")
_RE_IMPORT_NAMESPACE = re.compile(
    r"""import\s+\*\s+as\s+(\w+)\s+from\s*['"]([^'"]+)['"]""")
_RE_IMPORT_SIDE_EFFECT = re.compile(
    r"""import\s+['"]([^'"]+)['"]""")
_RE_EXPORT_FROM = re.compile(
    r"""export\s+\{[^}]*\}\s*from\s*['"]([^'"]+)['"]""")
_RE_REQUIRE = re.compile(
    r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")

# Function/method/class definition patterns
_RE_FUNCTION = re.compile(
    r"""(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(""")
_RE_ARROW_FUNC = re.compile(
    r"""(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>""")
_RE_METHOD = re.compile(
    r"""(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{""")
_RE_CLASS = re.compile(
    r"""class\s+(\w+)(?:\s+extends\s+(\w+))?""")

# Call patterns — simplified: detect Foo.bar(...), bar(...), platform.modules.call(...)
_RE_FUNC_CALL = re.compile(
    r"""(?:(\w+)\.)?(\w+)\s*\(""")

# platform.modules.call / call_capability patterns (module keys may contain hyphens)
_RE_PLATFORM_CALL = re.compile(
    r"""platform\s*\.\s*modules\s*\.\s*call\s*\(\s*['"]([\w-]+)['"]\s*,\s*['"]([\w-]+)['"]""")
_RE_CALL_CAPABILITY = re.compile(
    r"""call_capability\s*\(\s*['"]([\w-]+)['"]\s*,\s*['"]([\w-]+)['"]""")
_RE_REGISTER_CAPABILITY = re.compile(
    r"""register_capability\s*\(\s*['"]([\w-]+)['"]\s*,\s*['"]([\w-]+)['"]""")

# SQL table patterns in actual SQL/ORM contexts.
_SQL_TABLE_REF_RE = re.compile(
    r"""\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+["`]?([a-z][a-z0-9_]*_[a-z0-9_]+)["`]?""",
    re.IGNORECASE,
)
_SQL_DELETE_FROM_RE = re.compile(
    r"""\bDELETE\s+FROM\s+["`]?([a-z][a-z0-9_]*_[a-z0-9_]+)["`]?""",
    re.IGNORECASE,
)
_SQL_ALTER_TABLE_RE = re.compile(
    r"""\bALTER\s+TABLE\s+["`]?([a-z][a-z0-9_]*_[a-z0-9_]+)["`]?""",
    re.IGNORECASE,
)
_SQL_CREATE_TABLE_RE = re.compile(
    r"""\bCREATE\s+(?:TEMPORARY\s+|TEMP\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?([a-z][a-z0-9_]*_[a-z0-9_]+)["`]?""",
    re.IGNORECASE,
)
_SQL_CONTEXT_FUNCS = {
    "text",
    "sqlalchemy.text",
    "execute",
    "db.execute",
    "conn.execute",
    "connection.execute",
    "session.execute",
}

# Vue script block extraction
_RE_VUE_SCRIPT = re.compile(
    r"""<script\b[^>]*>(.*?)</script>""", re.DOTALL)


def _relative_path(absolute: Path) -> str:
    """Convert an absolute path to a project-relative path."""
    try:
        return str(absolute.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(absolute)


def _resolve_path(relative: str) -> Path:
    return (_PROJECT_ROOT / relative).resolve()


# ── Layer detection ─────────────────────────────────────────────────────────

def _detect_layer(path: str) -> tuple[str, str | None]:
    """Return (layer, module_key) for a project-relative file path."""
    if path.startswith("backend/app/"):
        return ("framework-backend", None)
    if path.startswith("frontend/src/"):
        return ("framework-frontend", None)
    if path.startswith("modules/"):
        parts = path.split("/")
        if len(parts) >= 2 and not parts[1].startswith("_"):
            return ("module", parts[1])
    return ("unknown", None)


def _detect_language(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        return "python"
    if ext == ".vue":
        return "vue"
    if ext in (".ts", ".tsx"):
        return "typescript"
    return ""


# ── Utility: resolve import path ────────────────────────────────────────────

def _resolve_import_path(source_file: str, import_spec: str) -> str | None:
    """Given a source file and an import specifier, try to resolve to a real file path.

    Handles:
      - Relative imports: './foo' -> source_dir/foo.{ts,py,etc}
      - Absolute module imports: 'app.services.foo' -> backend/app/services/foo.py
      - Module-to-module: '@/components/foo' -> frontend/src/components/foo.ts
    """
    if import_spec.startswith("."):
        # Relative import
        source_dir = _resolve_path(source_file).parent
        resolved = (source_dir / import_spec).resolve()
        for ext in _ALL_EXT:
            candidate = resolved.with_suffix(ext)
            if candidate.exists():
                return _relative_path(candidate)
            # index file
            idx = resolved / f"index{ext}"
            if idx.exists():
                return _relative_path(idx)
        # Try .py for relative
        candidate = resolved.with_suffix(".py")
        if candidate.exists():
            return _relative_path(candidate)
        candidate = resolved.with_suffix(".ts")
        if candidate.exists():
            return _relative_path(candidate)
        return None

    if import_spec.startswith("@"):
        # Alias — typically @/ maps to frontend/src/
        if import_spec.startswith("@/"):
            rest = import_spec[2:]
            for ext in _ALL_EXT:
                candidate = _PROJECT_ROOT / "frontend" / "src" / f"{rest}{ext}"
                if candidate.exists():
                    return _relative_path(candidate)
                idx = _PROJECT_ROOT / "frontend" / "src" / rest / f"index{ext}"
                if idx.exists():
                    return _relative_path(idx)
        return None

    # Absolute-like: "app.services.foo" -> "backend/app/services/foo.py"
    # Also: "modules.agent.backend.service" -> "modules/agent/backend/service.py"
    parts = import_spec.replace(".", "/")
    for base in ["backend", "frontend/src", "modules"]:
        candidate = _PROJECT_ROOT / base / f"{parts}.py"
        if candidate.exists():
            return _relative_path(candidate)
    # Try directly from project root (for "modules.xxx.yyy" style)
    candidate = _PROJECT_ROOT / f"{parts}.py"
    if candidate.exists():
        return _relative_path(candidate)
    # Try .ts extension
    for base in ["backend", "frontend/src", "modules"]:
        candidate = _PROJECT_ROOT / base / f"{parts}.ts"
        if candidate.exists():
            return _relative_path(candidate)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Python parser (ast)
# ═══════════════════════════════════════════════════════════════════════════════

class _PythonVisitor(ast.NodeVisitor):
    """Walk a Python AST and collect imports, definitions, calls, table refs."""

    def __init__(self, file_path: str, graph: CodeGraph):
        self.file_path = file_path
        self.graph = graph
        self._current_class: str | None = None
        self._function_stack: list[str] = []

    def _symbol_id(self, name: str) -> str:
        return f"{self.file_path}::{name}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            resolved = _resolve_import_path(self.file_path, alias.name)
            if resolved:
                layer, mod_key = _detect_layer(resolved)
                source_layer, source_mod = _detect_layer(self.file_path)
                cross_module = (source_layer == "module" and layer == "module"
                                and source_mod != mod_key)
                self.graph._ensure_file_node(resolved, layer, mod_key)
                self.graph.add_import(ImportEdge(
                    source=self.file_path, target=resolved,
                    cross_module=cross_module,
                    line=node.lineno,
                    imported_name=alias.name,
                ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            self.generic_visit(node)
            return
        # Resolve with the module path
        resolved = _resolve_import_path(self.file_path, node.module)
        if resolved:
            layer, mod_key = _detect_layer(resolved)
            source_layer, source_mod = _detect_layer(self.file_path)
            cross_module = (source_layer == "module" and layer == "module"
                            and source_mod != mod_key)
            self.graph._ensure_file_node(resolved, layer, mod_key)
            for alias in node.names:
                self.graph.add_import(ImportEdge(
                    source=self.file_path, target=resolved,
                    cross_module=cross_module,
                    line=node.lineno,
                    imported_name=f"{node.module}.{alias.name}",
                ))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prefix = f"{self._current_class}." if self._current_class else ""
        full_name = f"{prefix}{node.name}"
        sid = self._symbol_id(full_name)
        self.graph.add_symbol(sid, full_name, "function", self.file_path,
                              node.lineno, node.end_lineno or node.lineno)
        self._function_stack.append(full_name)

        # Walk body for calls & strings
        for child in ast.walk(node):
            self._visit_expr(child)

        self._function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        sid = self._symbol_id(node.name)
        self.graph.add_symbol(sid, node.name, "class", self.file_path,
                              node.lineno, node.end_lineno or node.lineno)
        for child in node.body:
            if isinstance(child, (ast.Assign, ast.AnnAssign)):
                self._handle_assign(child)
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def _visit_expr(self, node: ast.AST) -> None:
        """Check a node for calls, string table references, capability registrations."""
        if isinstance(node, ast.Call):
            self._handle_call(node)
        elif isinstance(node, ast.Assign):
            self._handle_assign(node)
        elif isinstance(node, ast.AnnAssign):
            self._handle_assign(node)

    def _handle_call(self, node: ast.Call) -> None:
        """Record function calls and capability registrations."""
        func_name = self._get_call_name(node)
        if not func_name:
            return

        # Always process capability registrations/calls (can be at module level)
        if func_name == "register_capability":
            self._parse_capability_call(node, "register")
        elif func_name == "call_capability":
            self._parse_capability_call(node, "call")

        # For regular function calls, need a caller context
        caller = self._function_stack[-1] if self._function_stack else None
        if caller and func_name not in ("register_capability", "call_capability"):
            target_id = self._resolve_call_target(func_name)
            if target_id:
                self.graph.add_call(CallEdge(
                    source_symbol_id=self._symbol_id(caller),
                    target_symbol_id=target_id,
                    source_line=node.lineno if hasattr(node, 'lineno') else 0,
                ))

        # Check args for SQL/ORM table references.
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                self._check_call_string(func_name, arg.value, node.lineno if hasattr(node, 'lineno') else 0)
        for kw in node.keywords:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                self._check_call_string(func_name, kw.value.value, node.lineno if hasattr(node, 'lineno') else 0)

    def _get_call_name(self, node: ast.Call) -> str | None:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            parts = []
            obj = node.func
            while isinstance(obj, ast.Attribute):
                parts.append(obj.attr)
                obj = obj.value
            if isinstance(obj, ast.Name):
                parts.append(obj.id)
            parts.reverse()
            return ".".join(parts)
        return None

    def _resolve_call_target(self, func_name: str) -> str | None:
        """Resolve a call target like 'service.do_thing' to a symbol ID."""
        # Simple case: same-file call
        candidate = self._symbol_id(func_name)
        if candidate in self.graph._symbols:
            return candidate
        # Cross-file: try to match by name
        for sid, sym in self.graph._symbols.items():
            if sym["name"] == func_name or sym["name"].endswith(f".{func_name}"):
                return sid
        return None

    def _parse_capability_call(self, node: ast.Call, kind: str) -> None:
        """Extract module and action from register_capability/call_capability calls."""
        args = node.args
        if kind == "register":
            # register_capability("module", "action", handler, ...)
            if len(args) >= 2:
                mod = args[0].value if isinstance(args[0], ast.Constant) else None
                act = args[1].value if isinstance(args[1], ast.Constant) else None
                if mod and act and isinstance(mod, str) and isinstance(act, str):
                    self.graph.add_capability(CapabilityEdge(
                        file=self.file_path, target=f"{mod}:{act}",
                        kind="register",
                        line=node.lineno if hasattr(node, 'lineno') else 0,
                    ))
        elif kind == "call":
            # call_capability("module", "action", ...)
            if len(args) >= 2:
                mod = args[0].value if isinstance(args[0], ast.Constant) else None
                act = args[1].value if isinstance(args[1], ast.Constant) else None
                if mod and act and isinstance(mod, str) and isinstance(act, str):
                    self.graph.add_capability(CapabilityEdge(
                        file=self.file_path, target=f"{mod}:{act}",
                        kind="call",
                        line=node.lineno if hasattr(node, 'lineno') else 0,
                    ))

    def _handle_assign(self, node: ast.Assign | ast.AnnAssign) -> None:
        """Extract ORM __tablename__ assignments."""
        value = node.value
        if isinstance(value, ast.Call):
            self._handle_call(value)
            return
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "__tablename__":
                self._add_db_table(value.value, node.lineno if hasattr(node, 'lineno') else 0)

    def _check_call_string(self, func_name: str, value: str, lineno: int) -> None:
        """Record table names only from real SQL/ORM call contexts."""
        if func_name in ("ForeignKey", "sqlalchemy.ForeignKey"):
            table_name = value.split(".", 1)[0]
            self._add_db_table(table_name, lineno)
            return
        if func_name in ("Table", "sqlalchemy.Table"):
            self._add_db_table(value, lineno)
            return
        if func_name in _SQL_CONTEXT_FUNCS:
            self._check_sql_string(value, lineno)

    def _check_sql_string(self, value: str, lineno: int) -> None:
        """Extract table names from SQL statements, not from arbitrary strings."""
        for pattern in (
            _SQL_TABLE_REF_RE,
            _SQL_DELETE_FROM_RE,
            _SQL_ALTER_TABLE_RE,
            _SQL_CREATE_TABLE_RE,
        ):
            for match in pattern.finditer(value):
                self._add_db_table(match.group(1), lineno)

    def _add_db_table(self, table_name: str, lineno: int) -> None:
        """Add a normalized DB table edge if it looks like a project table."""
        normalized = table_name.split(".", 1)[0].strip('"`').lower()
        if not re.fullmatch(r"(?:framework_|[a-z][a-z0-9]*_)[a-z0-9_]+", normalized):
            return
        self.graph.add_db_table(DbTableEdge(
            file=self.file_path, table_name=normalized, line=lineno,
        ))


def _parse_python(file_path: str, graph: CodeGraph) -> None:
    """Parse a Python file using ast and populate the graph."""
    abs_path = _resolve_path(file_path)
    source = abs_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(abs_path))

    layer, mod_key = _detect_layer(file_path)
    lang = _detect_language(file_path)
    graph._ensure_file_node(file_path, layer, mod_key, lang)

    visitor = _PythonVisitor(file_path, graph)
    visitor.visit(tree)

    # Also scan module-level calls (not inside any function/class body)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Expr, ast.Assign, ast.AnnAssign)):
            # Walk the expression for calls at module level
            for child in ast.walk(node):
                visitor._visit_expr(child)
        elif isinstance(node, ast.FunctionDef):
            pass  # Already handled by visitor
        elif isinstance(node, ast.ClassDef):
            pass  # Already handled by visitor
        elif isinstance(node, ast.Import):
            pass  # Already handled by visitor
        elif isinstance(node, ast.ImportFrom):
            pass  # Already handled by visitor


# ═══════════════════════════════════════════════════════════════════════════════
# TypeScript / Vue parser (tree-sitter AST — precise, no regex guesswork)
# ═══════════════════════════════════════════════════════════════════════════════

# Lazy-loaded tree-sitter Language instances
_ts_language = None
_ts_parser = None
_ts_parser_lock = threading.Lock()


def _ensure_ts_parser():
    """Lazy-init the tree-sitter TypeScript parser (thread-safe)."""
    global _ts_language, _ts_parser
    if _ts_parser is not None:
        return _ts_parser
    with _ts_parser_lock:
        if _ts_parser is not None:
            return _ts_parser
        try:
            import tree_sitter_typescript
            from tree_sitter import Language, Parser
        except ImportError as exc:
            logger.warning("tree-sitter-typescript not available, TS/Vue parsing disabled: %s", exc)
            _ts_parser = False
            return None

        try:
            _ts_language = Language(tree_sitter_typescript.language_typescript())
            _ts_parser = Parser(_ts_language)
            logger.info("tree-sitter TypeScript parser initialized")
        except Exception as exc:
            logger.warning("Failed to init tree-sitter: %s", exc)
            _ts_parser = False
            return None
    return _ts_parser


def _parse_typescript_source(source: str, file_path: str, graph: CodeGraph) -> None:
    """Parse TypeScript source using tree-sitter AST."""
    layer, mod_key = _detect_layer(file_path)
    lang = _detect_language(file_path)
    graph._ensure_file_node(file_path, layer, mod_key, lang)

    parser = _ensure_ts_parser()
    if not parser:
        # Fallback: minimal regex for critical patterns
        _parse_typescript_regex_fallback(source, file_path, graph)
        return

    src_bytes = source.encode("utf-8")
    tree = parser.parse(src_bytes)

    # Walk AST to collect imports, definitions, calls, strings
    _walk_ts_tree(tree.root_node, src_bytes, file_path, graph)


def _walk_ts_tree(node, src: bytes, file_path: str, graph: CodeGraph) -> None:
    """Recursively walk a tree-sitter AST node, collecting imports/defs/calls."""

    # ── Import statements ──────────────────────────────────────────────
    if node.type == "import_statement":
        # Extract the source path from the import clause
        source_clause = node.child_by_field_name("source")
        if source_clause and source_clause.type == "string":
            spec = _ts_string_value(source_clause, src)
            if spec:
                resolved = _resolve_import_path(file_path, spec)
                if resolved:
                    lineno = node.start_point[0] + 1
                    layer, mod_key = _detect_layer(resolved)
                    source_layer, source_mod = _detect_layer(file_path)
                    cross_module = (source_layer == "module" and layer == "module"
                                    and source_mod != mod_key)
                    graph._ensure_file_node(resolved, layer, mod_key)
                    graph.add_import(ImportEdge(
                        source=file_path, target=resolved,
                        cross_module=cross_module, line=lineno,
                    ))

    # ── Export ... from statements ─────────────────────────────────────
    elif node.type == "export_statement":
        source_clause = node.child_by_field_name("source")
        if source_clause and source_clause.type == "string":
            spec = _ts_string_value(source_clause, src)
            if spec:
                resolved = _resolve_import_path(file_path, spec)
                if resolved:
                    lineno = node.start_point[0] + 1
                    layer, mod_key = _detect_layer(resolved)
                    graph._ensure_file_node(resolved, layer, mod_key)
                    graph.add_import(ImportEdge(
                        source=file_path, target=resolved,
                        cross_module=False, line=lineno,
                    ))

    # ── Function declarations ──────────────────────────────────────────
    elif node.type == "function_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = src[name_node.start_byte:name_node.end_byte].decode()
            lineno = name_node.start_point[0] + 1
            end_lineno = node.end_point[0] + 1
            sid = f"{file_path}::{name}"
            graph.add_symbol(sid, name, "function", file_path, lineno, end_lineno)

    # ── Arrow functions in variable declarations ───────────────────────
    elif node.type == "lexical_declaration":
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                value_node = child.child_by_field_name("value")
                if name_node and value_node and value_node.type in (
                        "arrow_function", "function_expression"):
                    name = src[name_node.start_byte:name_node.end_byte].decode()
                    lineno = name_node.start_point[0] + 1
                    end_lineno = child.end_point[0] + 1
                    sid = f"{file_path}::{name}"
                    graph.add_symbol(sid, name, "function", file_path, lineno, end_lineno)

    # ── Class declarations ─────────────────────────────────────────────
    elif node.type == "class_declaration":
        name_node = node.child_by_field_name("name")
        if name_node:
            name = src[name_node.start_byte:name_node.end_byte].decode()
            lineno = name_node.start_point[0] + 1
            end_lineno = node.end_point[0] + 1
            sid = f"{file_path}::{name}"
            graph.add_symbol(sid, name, "class", file_path, lineno, end_lineno)

        # Walk class body for method definitions
        body = node.child_by_field_name("body")
        if body:
            _walk_class_body(body, src, file_path, name, graph)

    # ── Call expressions (for platform.modules.call detection) ─────────
    elif node.type == "call_expression":
        _check_ts_call_expr(node, src, file_path, graph)

    # ── SQL literals for table names ───────────────────────────────────
    elif node.type == "string":
        _check_ts_sql_string(node, src, file_path, graph)

    # Recurse into children
    for child in node.children:
        _walk_ts_tree(child, src, file_path, graph)


def _walk_class_body(body_node, src: bytes, file_path: str,
                     class_name: str, graph: CodeGraph) -> None:
    """Walk a class body for method definitions."""
    for child in body_node.children:
        if child.type == "method_definition":
            name_node = child.child_by_field_name("name")
            if name_node:
                method_name = src[name_node.start_byte:name_node.end_byte].decode()
                full_name = f"{class_name}.{method_name}"
                lineno = name_node.start_point[0] + 1
                end_lineno = child.end_point[0] + 1
                sid = f"{file_path}::{full_name}"
                graph.add_symbol(sid, full_name, "method", file_path, lineno, end_lineno)
        # Recurse for nested classes etc.
        for gc in child.children:
            if gc.type == "class_declaration":
                _walk_ts_tree(gc, src, file_path, graph)


def _check_ts_call_expr(node, src: bytes, file_path: str, graph: CodeGraph) -> None:
    """Check a call expression for platform.modules.call(...) patterns."""
    func_node = node.child_by_field_name("function")
    if not func_node:
        return

    # Build the dotted name: platform.modules.call
    parts = _ts_get_call_path(func_node, src)
    if not parts:
        return

    dotted = ".".join(parts)

    # register_capability / call_capability (Python-style)
    if dotted in ("register_capability", "call_capability"):
        kind = "register" if dotted == "register_capability" else "call"
        args_node = node.child_by_field_name("arguments")
        if args_node:
            strings = _ts_get_argument_strings(args_node, src)
            if len(strings) >= 2:
                graph.add_capability(CapabilityEdge(
                    file=file_path, target=f"{strings[0]}:{strings[1]}",
                    kind=kind,
                    line=node.start_point[0] + 1,
                ))

    # platform.modules.call(...)
    if dotted == "platform.modules.call":
        args_node = node.child_by_field_name("arguments")
        if args_node:
            strings = _ts_get_argument_strings(args_node, src)
            if len(strings) >= 2:
                graph.add_capability(CapabilityEdge(
                    file=file_path, target=f"{strings[0]}:{strings[1]}",
                    kind="call",
                    line=node.start_point[0] + 1,
                ))


def _ts_get_call_path(func_node, src: bytes) -> list[str] | None:
    """Resolve a dotted function call like platform.modules.call → ['platform', 'modules', 'call']."""
    if func_node.type == "identifier":
        return [src[func_node.start_byte:func_node.end_byte].decode()]
    if func_node.type == "member_expression":
        obj = func_node.child_by_field_name("object")
        prop = func_node.child_by_field_name("property")
        if obj and prop:
            obj_parts = _ts_get_call_path(obj, src)
            prop_name = src[prop.start_byte:prop.end_byte].decode()
            if obj_parts:
                return obj_parts + [prop_name]
            return [prop_name]
    return None


def _ts_get_argument_strings(args_node, src: bytes) -> list[str]:
    """Extract string literal arguments from a call arguments node."""
    result: list[str] = []
    for child in args_node.children:
        if child.type == "string":
            val = _ts_string_value(child, src)
            if val:
                result.append(val)
        elif child.type == "template_string":
            val = _ts_string_value(child, src)
            if val:
                result.append(val)
    return result


def _ts_string_value(string_node, src: bytes) -> str | None:
    """Extract the inner value of a tree-sitter string node."""
    text = src[string_node.start_byte:string_node.end_byte].decode()
    if len(text) >= 2:
        # Handle quoted strings: '...' or "..."
        if text[0] in ("'", '"') and text[-1] == text[0]:
            return text[1:-1]
        # Handle template strings: `...`
        if text[0] == "`" and text[-1] == "`":
            return text[1:-1]
    return text


def _check_ts_sql_string(string_node, src: bytes, file_path: str, graph: CodeGraph) -> None:
    """Extract table names only from SQL-looking TS string literals."""
    inner = _ts_string_value(string_node, src)
    if not inner:
        return
    if not re.search(r"\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|FROM|JOIN)\b", inner, re.IGNORECASE):
        return
    lineno = string_node.start_point[0] + 1
    for pattern in (
        _SQL_TABLE_REF_RE,
        _SQL_DELETE_FROM_RE,
        _SQL_ALTER_TABLE_RE,
        _SQL_CREATE_TABLE_RE,
    ):
        for match in pattern.finditer(inner):
            graph.add_db_table(DbTableEdge(
                file=file_path, table_name=match.group(1).lower(), line=lineno,
            ))


# ── Regex fallback for when tree-sitter is unavailable ───────────────────────

def _parse_typescript_regex_fallback(source: str, file_path: str,
                                     graph: CodeGraph) -> None:
    """Minimal regex-based TS/Vue parser (fallback only)."""
    layer, mod_key = _detect_layer(file_path)
    lang = _detect_language(file_path)
    graph._ensure_file_node(file_path, layer, mod_key, lang)

    for match in _RE_IMPORT_NAMED.finditer(source):
        spec = match.group(1)
        resolved = _resolve_import_path(file_path, spec)
        if resolved:
            _add_ts_import(graph, file_path, resolved, source, match.start())

    for match in _RE_IMPORT_DEFAULT.finditer(source):
        spec = match.group(2)
        resolved = _resolve_import_path(file_path, spec)
        if resolved:
            _add_ts_import(graph, file_path, resolved, source, match.start())

    for match in _RE_PLATFORM_CALL.finditer(source):
        target_module = match.group(1)
        action = match.group(2)
        lineno = source[:match.start()].count("\n") + 1
        graph.add_capability(CapabilityEdge(
            file=file_path, target=f"{target_module}:{action}",
            kind="call", line=lineno,
        ))


def _add_ts_import(graph: CodeGraph, source: str, target: str,
                   source_text: str, match_pos: int) -> None:
    lineno = source_text[:match_pos].count("\n") + 1
    layer, mod_key = _detect_layer(target)
    source_layer, source_mod = _detect_layer(source)
    cross_module = (source_layer == "module" and layer == "module"
                    and source_mod != mod_key)
    graph._ensure_file_node(target, layer, mod_key)
    graph.add_import(ImportEdge(
        source=source, target=target,
        cross_module=cross_module,
        line=lineno,
    ))


def _parse_typescript(file_path: str, graph: CodeGraph) -> None:
    abs_path = _resolve_path(file_path)
    source = abs_path.read_text(encoding="utf-8")
    _parse_typescript_source(source, file_path, graph)


def _parse_vue(file_path: str, graph: CodeGraph) -> None:
    """Parse a Vue SFC: extract <script> blocks, parse as TypeScript."""
    abs_path = _resolve_path(file_path)
    source = abs_path.read_text(encoding="utf-8")

    layer, mod_key = _detect_layer(file_path)
    graph._ensure_file_node(file_path, layer, mod_key, "vue")

    # Extract all <script> blocks (including <script setup>)
    for match in _RE_VUE_SCRIPT.finditer(source):
        script_content = match.group(1)
        _parse_typescript_source(script_content, file_path, graph)


# ═══════════════════════════════════════════════════════════════════════════════
# File scanner
# ═══════════════════════════════════════════════════════════════════════════════

def _should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from scanning."""
    parts = set(path.parts)
    if parts & _EXCLUDE_PATH_PARTS:
        return True
    if path.name.startswith("."):
        return True
    if path.is_dir() and path.name in _EXCLUDE_DIRS:
        return True
    return False


def _scan_files() -> list[str]:
    """Walk the three scan roots and collect all source files.

    Returns list of project-relative paths.
    """
    files: list[str] = []
    for root_name in _SCAN_ROOTS:
        root_path = _PROJECT_ROOT / root_name
        if not root_path.exists():
            logger.warning("Scan root not found: %s", root_path)
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Filter out excluded directories in-place
            dirnames[:] = [d for d in dirnames
                           if not _should_exclude(Path(dirpath) / d)]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                if _should_exclude(fpath):
                    continue
                ext = fpath.suffix.lower()
                if ext in _ALL_EXT:
                    files.append(_relative_path(fpath))
    return files


# ═══════════════════════════════════════════════════════════════════════════════
# Parser dispatch
# ═══════════════════════════════════════════════════════════════════════════════

_PARSERS = {
    ".py": _parse_python,
    ".ts": _parse_typescript,
    ".tsx": _parse_typescript,
    ".vue": _parse_vue,
}


def _parse_file(file_path: str, graph: CodeGraph) -> None:
    """Parse a single file into the graph."""
    ext = os.path.splitext(file_path)[1].lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        return
    try:
        parser(file_path, graph)
        graph.record_file_index(file_path)
    except Exception as exc:
        logger.warning("Parse error in %s: %s", file_path, exc)
        graph.record_file_fail(file_path, str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# Indexer controller
# ═══════════════════════════════════════════════════════════════════════════════

class CodeIndexer:
    """Controls full and incremental index builds."""

    def __init__(self, graph: CodeGraph | None = None):
        self.graph = graph or get_graph()
        self._build_thread: threading.Thread | None = None

    def build_full(self) -> None:
        """Build the full index from scratch (synchronous)."""
        logger.info("Starting full index build...")
        self.graph.begin_build()
        files = _scan_files()
        logger.info("Scan found %d files", len(files))

        for i, fpath in enumerate(files):
            _parse_file(fpath, self.graph)
            if (i + 1) % 50 == 0:
                logger.info("Indexed %d/%d files", i + 1, len(files))

        self.graph.finish_build(len(files))
        logger.info("Full index build complete: %d files, %d symbols",
                     len(self.graph._files), len(self.graph._symbols))

    def build_async(self) -> None:
        """Build in a background thread."""
        if self._build_thread and self._build_thread.is_alive():
            logger.info("Build already in progress")
            return
        self._build_thread = threading.Thread(target=self.build_full, daemon=True)
        self._build_thread.start()

    def update_file(self, file_path: str) -> None:
        """Incrementally re-index a single file."""
        logger.debug("Incremental update: %s", file_path)
        self.graph.clear_file(file_path)
        abs_path = _resolve_path(file_path)
        if abs_path.exists():
            _parse_file(file_path, self.graph)
        self.graph._file_count_at_build = len(self.graph._files)

    def remove_file(self, file_path: str) -> None:
        """Remove a deleted file from the index."""
        logger.debug("Removing from index: %s", file_path)
        self.graph.clear_file(file_path)
        self.graph._file_count_at_build = len(self.graph._files)


# Singleton
_indexer_instance: CodeIndexer | None = None


def get_indexer() -> CodeIndexer:
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = CodeIndexer()
    return _indexer_instance
