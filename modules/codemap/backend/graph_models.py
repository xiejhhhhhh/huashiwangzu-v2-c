"""CodeGraph data model classes.

Extracted from graph.py to follow size guidelines.
"""
from dataclasses import dataclass, field


class ImportEdge:
    source: str       # file path
    target: str       # file path
    cross_module: bool = False
    compliant: bool | None = None  # None = not a cross-boundary scenario
    line: int = 0
    imported_name: str = ""

    def to_dict(self) -> dict:
        d = {"source": self.source, "target": self.target,
             "cross_module": self.cross_module, "line": self.line}
        if self.imported_name:
            d["imported_name"] = self.imported_name
        if self.compliant is not None:
            d["compliant"] = self.compliant
        return d


@dataclass
class CallEdge:
    source_symbol_id: str
    target_symbol_id: str
    source_line: int = 0

    def to_dict(self) -> dict:
        return {"source_symbol_id": self.source_symbol_id,
                "target_symbol_id": self.target_symbol_id,
                "source_line": self.source_line}


@dataclass
class CapabilityEdge:
    file: str          # source file
    target: str        # "module:action"
    kind: str          # "register" | "call"
    line: int = 0

    def to_dict(self) -> dict:
        return {"file": self.file, "target": self.target, "kind": self.kind, "line": self.line}


@dataclass
class DbTableEdge:
    file: str
    table_name: str
    line: int = 0

    def to_dict(self) -> dict:
        return {"file": self.file, "table_name": self.table_name, "line": self.line}


# ── File node ───────────────────────────────────────────────────────────────

@dataclass
class FileNode:
    path: str          # relative to project root
    layer: str         # "framework-backend" | "framework-frontend" | "module"
    module_key: str | None = None
    language: str = ""
    symbols: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "layer": self.layer,
            "module_key": self.module_key,
            "language": self.language,
            "symbol_count": len(self.symbols),
            "symbols": self.symbols,
        }


# ── The graph ───────────────────────────────────────────────────────────────