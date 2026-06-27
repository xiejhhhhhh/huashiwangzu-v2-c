"""Tool orchestration for agent module: partition, concurrent read + serial write.

Replaces inline tool execution in ``chat.py`` with a structured orchestrator
that classifies each tool by metadata, schedules read tools concurrently via
a semaphore-controlled pool, executes write/destructive tools serially, and
isolates per-tool failures so one failure does not abort the batch.

Metadata resolution order:
  1. Explicit tool-level metadata (registered via ``register_tool_metadata``).
  2. Capability registry (``list_capabilities``) — ``brief`` / ``description``
     hints.
  3. Name pattern matching (fallback, same as before).
  4. Unknown tools default to write + serial (conservative).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any, Callable

logger = logging.getLogger("v2.agent").getChild("engine.tool_orchestrator")

_DEFAULT_MAX_CONCURRENCY = 8


# ── Tool metadata ───────────────────────────────────────────────────────


@dataclass
class ToolMetadata:
    """Classification metadata describing how a tool should be executed.

    Attributes:
        name_pattern: The glob pattern or prefix that matched this tool.
        read_only: True if the tool only reads data (no mutation).
        concurrency_safe: True if the tool can safely run in parallel.
        write: True if the tool mutates state (save, update, create, etc.).
        destructive: True if the tool destroys data (delete, remove, etc.).
        requires_serial: True if the tool must run alone, not interleaved
            with other tools of the same batch.
    """

    name_pattern: str = ""
    read_only: bool = False
    concurrency_safe: bool = False
    write: bool = False
    destructive: bool = False
    requires_serial: bool = False


# ── Explicit tool metadata registry (metadata-first) ────────────────────
#
# Tools can declare their execution semantics explicitly here,
# bypassing name-pattern guessing.  This is the "metadata-first"
# approach: orchestrator checks this dict before pattern matching.

_EXPLICIT_METADATA: dict[str, ToolMetadata] = {}


def register_tool_metadata(tool_name: str, meta: ToolMetadata) -> None:
    """Register explicit execution metadata for a tool.

    Args:
        tool_name: The full tool name (e.g. ``knowledge__search``).
        meta: The metadata describing how this tool should be executed.
    """
    _EXPLICIT_METADATA[tool_name] = meta
    logger.debug("Registered explicit metadata for tool '%s': %s", tool_name, meta)


# ── Default registrations for known tools ───────────────────────────
# These are called at module init so the orchestrator never has to
# guess their semantics.  Everything not listed here still works:
# it falls back to capability registry → pattern matching → conservative default.

_read_tools: list[str] = [
    # Knowledge module — pure reads (names match register_capability)
    "knowledge__search",
    "knowledge__get_block",
    "knowledge__get_page_fusion",
    "knowledge__get_entity_dictionary",
    "knowledge__get_graph_context",
    "knowledge__get_pending_count",
    "knowledge__get_evidence_detail",
    "knowledge__get_ocr_words",
    # Memory module — mostly reads (names match register_capability)
    "memory__recall",
    "memory__recall_stable_rules",
    "memory__recall_chunk",
    "memory__list",
    "memory__match_experience",
    "memory__overview_stats",
    "memory__fuse",
    # Agent self-inspection — pure reads
    "agent__get_system_prompt",
    "agent__get_enterprise_prompt",
    "agent__get_my_profile",
    # Web tools — reads
    "web-tools__search",
    "web-tools__fetch",
    # File viewing — reads (names match register_capability)
    "text-parser__parse",
    "pdf-parser__parse",
    "docx-parser__parse",
    "pptx-parser__parse",
    "xlsx-parser__parse",
    "image-vision__describe",
    # Scheduler — reads (names match register_capability)
    "scheduler__list",
    # Docs-open — reads (names match register_capability)
    "docs-open__get_content",
    # Codemap — reads (names match register_capability)
    "codemap__get_file",
    "codemap__impact",
    "codemap__search",
    "codemap__stats",
    "codemap__module_map",
    "codemap__check_boundary",
    "codemap__check_lock",
    "codemap__list_locks",
    "codemap__list_feedback",
    # Desktop tools — reads
    "desktop-tools__list_files",
    "desktop-tools__search_files",
    "desktop-tools__read_file",
    "desktop-tools__list_apps",
    # Terminal tools — reads
    "terminal-tools__read_file",
    "terminal-tools__list_workspace",
    # Image generation — reads
    "image-gen__list_templates",
    "image-gen__usage_history",
    # Excel engine — reads
    "excel-engine__parse",
    # Docs-open — reads
    "docs-open__open",
]

_write_tools: list[str] = [
    # Memory module — writes (names match register_capability)
    "memory__save",
    "memory__save_stable_rule",
    "memory__save_experience",
    "memory__rethink",
    "memory__replace",
    "memory__insert",
    "memory__experience_feedback",
    "memory__dream",
    # Agent profile — writes
    "agent__update_my_profile",
    "agent__update_system_prompt",
    "agent__update_enterprise_prompt",
    # Office generation — writes (names match register_capability)
    "office-gen__docx",
    "office-gen__xlsx",
    "office-gen__pptx",
    "office-gen__pdf",
    "office-gen__convert",
    # Image generation — writes
    "image-gen__generate",
    # Terminal — serial writes (names match register_capability)
    "terminal-tools__exec",
    "terminal-tools__write_file",
    "terminal-tools__run_python",
    "terminal-tools__publish",
    "terminal-tools__import",
    "terminal-tools__chart",
    # Desktop tools — writes (other desktop mutation tools)
    # Scheduler — writes (names match register_capability)
    "scheduler__create",
    "scheduler__cancel",
    # Docs-open — writes (names match register_capability)
    "docs-open__create_doc",
    # IM — writes (names match register_capability)
    "im__notify",
    "im__send",
    # Agent — writes
    "agent__spawn_subagent",
    # Codemap — writes (index rebuild)
    "codemap__rebuild",
    "codemap__acquire_lock",
    "codemap__release_lock",
    "codemap__report_inaccuracy",
    # Knowledge — writes
    "knowledge__ingest",
]

_destructive_tools: list[str] = [
    "memory__delete",
]


def _register_default_metadata() -> None:
    """Register metadata for all tools in the above lists.

    Called once at module init.  After that, individual modules can
    override or add more tools via ``register_tool_metadata``.
    """
    for name in _read_tools:
        register_tool_metadata(
            name,
            ToolMetadata(name_pattern=name, read_only=True, concurrency_safe=True),
        )
    for name in _write_tools:
        register_tool_metadata(
            name,
            ToolMetadata(name_pattern=name, write=True, requires_serial=True),
        )
    for name in _destructive_tools:
        register_tool_metadata(
            name,
            ToolMetadata(name_pattern=name, destructive=True, requires_serial=True),
        )
    logger.info(
        "Registered default metadata: %d read, %d write, %d destructive",
        len(_read_tools), len(_write_tools), len(_destructive_tools),
    )


_register_default_metadata()

# ── Pattern definitions (priority: destructive > write > read) ──────────

_READ_PATTERNS: list[str] = [
    "*search*",
    "*list*",
    "*describe*",
    "get_*",
    "*read*",
    "*recall*",
    "skill_list",
    "skill_describe",
    "*capabilities*",
    "*health*",
]

_WRITE_PATTERNS: list[str] = [
    "*save*",
    "*write*",
    "*update*",
    "*create*",
    "set_*",
    "add_*",
]

_DESTRUCTIVE_PATTERNS: list[str] = [
    "*delete*",
    "*remove*",
    "*clear*",
    "*reset*",
    "*destroy*",
]


def _match_any(name: str, patterns: list[str]) -> bool:
    """Return True when *name* matches any glob pattern in *patterns*."""
    for pat in patterns:
        if fnmatch(name.lower(), pat.lower()):
            return True
    return False


def _try_get_capability_metadata(tool_name: str) -> ToolMetadata | None:
    """Try to classify a tool via capability registry metadata.

    Checks the global capability registry for ``brief`` / ``description``
    hints that indicate read-only or write semantics.
    """
    try:
        from app.services.module_registry import list_capabilities
        cap_list = list_capabilities()
        # Resolve tool name → module:action
        module_key, _, action = tool_name.partition("__")
        if not action:
            action = module_key
            module_key = ""
        matched = None
        for entry in cap_list:
            if entry.get("module") == module_key and entry.get("action") == action:
                matched = entry
                break
        if not matched:
            # Try matching the raw tool_name as module:action
            for entry in cap_list:
                full = f"{entry.get('module', '')}:{entry.get('action', '')}"
                if full == tool_name or full == tool_name.replace("__", ":"):
                    matched = entry
                    break

        if matched:
            desc = (matched.get("description") or "").lower()
            brief = (matched.get("brief") or "").lower()
            combined = f"{desc} {brief}"

            read_hints = {"search", "list", "get", "read", "recall", "query", "describe", "find"}
            write_hints = {"save", "create", "update", "write", "set", "add", "insert"}
            destructive_hints = {"delete", "remove", "clear", "reset", "destroy"}

            is_read = any(h in combined for h in read_hints)
            is_write = any(h in combined for h in write_hints)
            is_destructive = any(h in combined for h in destructive_hints)

            if is_destructive:
                return ToolMetadata(
                    name_pattern=tool_name,
                    destructive=True,
                    requires_serial=True,
                )
            if is_write and not is_read:
                return ToolMetadata(
                    name_pattern=tool_name,
                    write=True,
                    requires_serial=True,
                )
            if is_read and not is_write:
                return ToolMetadata(
                    name_pattern=tool_name,
                    read_only=True,
                    concurrency_safe=True,
                )
    except Exception:
        logger.debug("Capability registry lookup failed for '%s'; falling back to patterns", tool_name)
    return None


def determine_tool_metadata(tool_name: str) -> ToolMetadata:
    """Classify a tool, using metadata-first resolution.

    Resolution order:
      1. Explicit ``register_tool_metadata`` dictionary.
      2. Capability registry ``brief``/``description`` hints.
      3. Name pattern matching (destructive → write → read).
      4. Unknown tools default to write + serial (conservative safety).

    Args:
        tool_name: The full tool/function name
            (e.g. ``knowledge__search``, ``memory__save``, ``delete_file``).

    Returns:
        A ToolMetadata describing the tool's execution characteristics.
    """
    # 1. Explicit metadata
    explicit = _EXPLICIT_METADATA.get(tool_name)
    if explicit is not None:
        logger.debug("Metadata-first: explicit match for '%s': %s", tool_name, explicit)
        return explicit

    # 2. Capability registry metadata
    cap_meta = _try_get_capability_metadata(tool_name)
    if cap_meta is not None:
        logger.debug("Metadata-first: capability registry match for '%s': %s", tool_name, cap_meta)
        return cap_meta

    # 3. Name pattern matching
    name = tool_name.lower()

    if _match_any(name, _DESTRUCTIVE_PATTERNS):
        return ToolMetadata(
            name_pattern=tool_name,
            destructive=True,
            requires_serial=True,
        )

    if _match_any(name, _WRITE_PATTERNS):
        return ToolMetadata(
            name_pattern=tool_name,
            write=True,
            requires_serial=True,
        )

    if _match_any(name, _READ_PATTERNS):
        return ToolMetadata(
            name_pattern=tool_name,
            read_only=True,
            concurrency_safe=True,
        )

    logger.debug(
        "Unknown tool '%s' — defaulting to write+serial (no metadata, no pattern)",
        tool_name,
    )
    return ToolMetadata(
        name_pattern=tool_name,
        write=True,
        requires_serial=True,
    )


# ── Orchestrator ────────────────────────────────────────────────────────


class ToolOrchestrator:
    """Schedule tool batch execution with appropriate concurrency.

    Partitioning strategy:

    1. Every tool is classified via :meth:`determine_tool_metadata`.
    2. Read/concurrency-safe tools are executed concurrently, throttled by
       a semaphore (default max concurrency = 8).
    3. Write and destructive tools are executed serially.
    4. Results are collected in the original input order — one failure
       does not abort the remaining tools.

    Usage::

        orchestrator = ToolOrchestrator(max_concurrency=8)
        results = await orchestrator.execute_batch(tools, my_execute_fn)
        for r in results:
            print(r["name"], r.get("result") or r.get("error"))
    """

    def __init__(self, max_concurrency: int = _DEFAULT_MAX_CONCURRENCY) -> None:
        self._max_concurrency = max_concurrency
        self._logger = logger.getChild("ToolOrchestrator")

    @property
    def max_concurrency(self) -> int:
        """The maximum number of concurrent read tools allowed."""
        return self._max_concurrency

    def determine_tool_metadata(self, tool_name: str) -> ToolMetadata:
        """Classify a tool name.  Delegates to the module-level function."""
        return determine_tool_metadata(tool_name)

    async def execute_batch(
        self,
        tools: list[dict],
        execute_fn: Callable[[dict], Any],
    ) -> list[dict]:
        """Execute a batch of tool calls with automatic concurrency management.

        Args:
            tools: List of tool-call dicts.  Each must contain at least:
                ``name`` (the tool/function name),
                ``tool_call_id`` (unique per-call identifier),
                ``args`` (arguments dict passed to the tool).

            execute_fn: Async callable invoked once per tool.  It receives
                the full tool dict and should return a result dict (or raise
                an exception on failure).  The orchestrator catches exceptions
                and serializes them as ``{"error": "..."}`` in the result —
                they are **not** propagated to the caller.

        Returns:
            A list of result dicts in the same order as *tools*.  Each entry
            always contains ``name`` and ``tool_call_id``, and either
            ``result`` (on success) or ``error`` (on failure).
        """
        if not tools:
            return []

        # 1. Classify every tool
        indexed: list[tuple[int, dict, ToolMetadata]] = []
        for i, tool in enumerate(tools):
            name = tool.get("name", "")
            meta = self.determine_tool_metadata(name)
            indexed.append((i, tool, meta))

        # 2. Results container — preserve original order.
        #
        # Important: write/destructive tools are order barriers. A later read
        # must not run before an earlier write, otherwise a model-requested
        # "save then recall" sequence can observe stale state. We therefore
        # execute consecutive read-only runs concurrently, and execute every
        # serial tool in its original position.
        results: list[dict | None] = [None] * len(tools)

        async def _execute_safe(tool: dict, meta: ToolMetadata) -> dict:
            """Execute one tool and capture exceptions in the result dict."""
            name = tool.get("name", "")
            tool_call_id = tool.get("tool_call_id", "")
            try:
                self._logger.debug("Executing tool '%s' (id=%s)", name, tool_call_id)
                result = await execute_fn(tool)
                return {
                    "name": name,
                    "tool_call_id": tool_call_id,
                    "result": result,
                }
            except asyncio.CancelledError:
                self._logger.warning("Tool '%s' cancelled", name)
                raise
            except Exception as exc:
                self._logger.warning("Tool '%s' failed: %s", name, str(exc)[:500])
                return {
                    "name": name,
                    "tool_call_id": tool_call_id,
                    "error": str(exc),
                }

        async def _run_read_batch(read_batch: list[tuple[int, dict, ToolMetadata]]) -> None:
            if not read_batch:
                return
            semaphore = asyncio.Semaphore(self._max_concurrency)

            async def _run_with_semaphore(
                idx: int,
                tool: dict,
                meta: ToolMetadata,
            ) -> tuple[int, dict]:
                async with semaphore:
                    outcome = await _execute_safe(tool, meta)
                    return idx, outcome

            read_coros = [
                _run_with_semaphore(idx, tool, meta)
                for idx, tool, meta in read_batch
            ]

            completed = await asyncio.gather(*read_coros, return_exceptions=True)

            for item in completed:
                if isinstance(item, BaseException):
                    self._logger.error(
                        "Unexpected exception in read batch: %s", item,
                    )
                    continue
                idx, outcome = item
                results[idx] = outcome

            self._logger.info("Read batch completed (%d tools)", len(read_batch))

        # 3. Walk in original order. Read-only runs can batch; writes and
        #    destructive tools flush the pending read batch then execute alone.
        read_batch: list[tuple[int, dict, ToolMetadata]] = []
        serial_count = 0
        read_count = 0
        for idx, tool, meta in indexed:
            if meta.concurrency_safe and meta.read_only:
                read_batch.append((idx, tool, meta))
                read_count += 1
                continue

            await _run_read_batch(read_batch)
            read_batch = []
            serial_count += 1
            outcome = await _execute_safe(tool, meta)
            results[idx] = outcome

        await _run_read_batch(read_batch)

        if serial_count:
            self._logger.info("Serial tools completed (%d tools)", serial_count)
        self._logger.info(
            "Batch completed: %d total, %d read, %d serial, max_concurrency=%d",
            len(tools),
            read_count,
            serial_count,
            self._max_concurrency,
        )
        # 4. Defensive fill — should never be needed, but protects against
        #    logic bugs.
        final_results: list[dict] = []
        for i, r in enumerate(results):
            if r is None:
                name = tools[i].get("name", "") if i < len(tools) else "unknown"
                tid = tools[i].get("tool_call_id", "") if i < len(tools) else ""
                self._logger.error("Result slot %d was None (tool=%s)", i, name)
                final_results.append({
                    "name": name,
                    "tool_call_id": tid,
                    "error": "Orchestrator internal error: result not produced",
                })
            else:
                final_results.append(r)

        return final_results
