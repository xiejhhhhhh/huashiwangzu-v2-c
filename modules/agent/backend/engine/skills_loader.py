"""Markdown-based skill discovery and loading for the Agent runtime.

Skills are defined in markdown files with YAML frontmatter, auto-discovered
from a directory tree.  This replaces hardcoded skill registrations with
file-based convention.
"""
from __future__ import annotations

import fnmatch
import html
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("v2.agent").getChild("engine.skills_loader")

DEFAULT_BASE_DIR = "data/skills"
DEFAULT_CACHE_TTL: float = 60.0


@dataclass
class SkillDef:
    """A single skill discovered from a markdown file."""

    name: str
    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    hooks: dict = field(default_factory=dict)
    agent: str = ""
    effort: int = 3
    body: str = ""
    file_path: str = ""
    enabled: bool = True
    scope: str = "global"      # "workspace" | "project" | "global"; set by discoverer
    priority: int = 0          # higher = wins when name collides


# ── Priority resolution order ──────────────────────────────────────────
#
# When the same skill name appears in multiple scopes, the highest-priority
# scope wins.  Within the same scope, explicit ``priority`` frontmatter
# breaks ties (higher wins).

_SCOPE_ORDER = {"workspace": 3, "project": 2, "global": 1}


def resolve_skill_priority(skills: list[SkillDef]) -> list[SkillDef]:
    """Deduplicate skills by name, keeping the highest-priority variant.

    Priority rules:
    1. ``workspace`` beats ``project`` beats ``global``.
    2. Within the same scope, explicit ``priority`` frontmatter wins.
    3. If everything is equal, the first discovered wins (stable sort).

    Returns a new list with duplicates removed.
    """
    best: dict[str, SkillDef] = {}
    for skill in skills:
        existing = best.get(skill.name)
        if existing is None:
            best[skill.name] = skill
            continue
        existing_scope_rank = _SCOPE_ORDER.get(existing.scope, 0)
        skill_scope_rank = _SCOPE_ORDER.get(skill.scope, 0)
        if skill_scope_rank > existing_scope_rank:
            best[skill.name] = skill
        elif skill_scope_rank == existing_scope_rank and skill.priority > existing.priority:
            best[skill.name] = skill
    return list(best.values())


def _parse_frontmatter(content: str) -> tuple[Optional[dict], str]:
    """Extract YAML frontmatter and body from a string.

    Expects content starting with ``---``, then YAML, then ``---``, then the
    markdown body.  Returns ``(frontmatter_dict, body)``.  If no valid
    frontmatter is found, returns ``(None, content)``.
    """
    stripped = content.lstrip("\ufeff").lstrip()
    if not stripped.startswith("---"):
        return None, content

    # Find the closing ---
    end_idx = stripped.find("---", 3)
    if end_idx == -1:
        return None, content

    yaml_block = stripped[3:end_idx]
    body = stripped[end_idx + 3:].lstrip("\n")

    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        logger.warning("Failed to parse YAML frontmatter", exc_info=True)
        return None, content

    if not isinstance(parsed, dict):
        return None, content

    return parsed, body


class SkillsLoader:
    """Discover, cache, and query skills from markdown files."""

    def __init__(self, base_dir: str = DEFAULT_BASE_DIR, cache_ttl: float = DEFAULT_CACHE_TTL) -> None:
        self.base_dir = Path(base_dir)
        self.cache_ttl = cache_ttl
        self._cached_skills: list[SkillDef] = []
        self._cache_loaded_at: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_skills(self, base_dir: str | None = None, scope: str = "global") -> list[SkillDef]:
        """Scan *base_dir* (or the instance default) recursively for every
        ``.md`` file, parse its YAML frontmatter and return a list of
        :class:`SkillDef` instances.

        Args:
            base_dir: Directory to scan.  Defaults to the instance default.
            scope: The scope label to assign (``"workspace"`` / ``"project"`` / ``"global"``).

        Results are cached for ``cache_ttl`` seconds to avoid re-reading
        the filesystem on every call.
        """
        resolve_dir = Path(base_dir) if base_dir is not None else self.base_dir

        if self._is_cache_valid(resolve_dir):
            return list(self._cached_skills)

        if not resolve_dir.exists():
            logger.info("Skills directory %s does not exist; returning empty list", resolve_dir)
            self._cached_skills = []
            self._cache_loaded_at = time.time()
            return list(self._cached_skills)

        if not resolve_dir.is_dir():
            logger.warning("Skills path %s is not a directory; returning empty list", resolve_dir)
            self._cached_skills = []
            self._cache_loaded_at = time.time()
            return list(self._cached_skills)

        skills: list[SkillDef] = []
        md_files = sorted(resolve_dir.rglob("*.md"))

        for md_path in md_files:
            try:
                skill = self._load_skill(md_path)
                if skill is not None:
                    skill.scope = scope
                    skills.append(skill)
            except Exception:
                logger.exception("Error loading skill from %s; skipping", md_path)

        self._cached_skills = skills
        self._cache_loaded_at = time.time()
        return list(skills)

    def match_skills(self, skills: list[SkillDef], current_path: str) -> list[SkillDef]:
        """Return only skills whose ``paths`` patterns match *current_path*.

        Each pattern in ``skill.paths`` is tested with :func:`fnmatch.fnmatch`.
        A skill with no ``paths`` configured is considered a match (match-all).

        Rules:
        - Skills without ``paths`` are **global**: always matched.
        - Skills with ``paths`` are **scoped**: only matched when ``current_path``
          is non-empty and matches at least one pattern.
        - An empty ``current_path`` never matches path-scoped skills.
        """
        matched: list[SkillDef] = []
        for skill in skills:
            if not skill.enabled:
                continue
            if not skill.paths:
                matched.append(skill)
                continue
            if not current_path:
                logger.debug(
                    "skill '%s' has path constraints but current_path is empty; skipping",
                    skill.name,
                )
                continue
            for pattern in skill.paths:
                if fnmatch.fnmatch(current_path, pattern):
                    matched.append(skill)
                    break
        return matched

    def format_skills_for_prompt(self, skills: list[SkillDef]) -> str:
        """Format a list of :class:`SkillDef` into a prompt-injection string.

        All user-supplied content is HTML-escaped to prevent prompt structure
        breakage.  Returns an empty string when *skills* is empty.
        """
        if not skills:
            return ""

        blocks: list[str] = []
        for s in skills:
            name = html.escape(s.name, quote=True)
            description = html.escape(s.description)
            allowed_tools = [html.escape(t) for t in s.allowed_tools]
            body_raw = s.body.strip() if s.body else ""
            # Escape content and also replace </skill> sequences within body
            # to prevent premature closure of the outer XML tag.
            body = html.escape(body_raw).replace("&lt;/skill&gt;", "&lt;\\/skill&gt;")

            lines = [f"<skill name=\"{name}\">"]
            if s.description:
                lines.append(f"  <description>{description}</description>")
            if s.allowed_tools:
                tools = ", ".join(allowed_tools)
                lines.append(f"  <allowed-tools>{tools}</allowed-tools>")
            if s.effort:
                lines.append(f"  <effort>{s.effort}</effort>")
            if s.body:
                lines.append(f"  <instructions>\n{body}\n  </instructions>")
            lines.append("</skill>")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _is_cache_valid(self, resolve_dir: Path) -> bool:
        if not self._cached_skills:
            return False
        if resolve_dir != self.base_dir:
            return False
        return (time.time() - self._cache_loaded_at) < self.cache_ttl

    def invalidate_cache(self) -> None:
        """Force the next ``find_skills`` call to re-read from disk."""
        self._cached_skills = []
        self._cache_loaded_at = 0.0

    # ------------------------------------------------------------------
    # Single-file loader
    # ------------------------------------------------------------------

    def _load_skill(self, md_path: Path) -> SkillDef | None:
        """Read a single markdown file and convert it to a :class:`SkillDef`.

        Returns ``None`` if the file has no valid frontmatter or lacks an
        ``name`` field.
        """
        raw = md_path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(raw)

        if frontmatter is None:
            return None

        name = frontmatter.get("name", "")
        if not name:
            logger.debug("Skipping %s: no 'name' in frontmatter", md_path)
            return None

        allowed_tools_raw = frontmatter.get("allowed-tools", frontmatter.get("allowed_tools", []))
        if isinstance(allowed_tools_raw, str):
            allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]
        else:
            allowed_tools = list(allowed_tools_raw) if isinstance(allowed_tools_raw, list) else []

        paths_raw = frontmatter.get("paths", [])
        if isinstance(paths_raw, str):
            paths = [p.strip() for p in paths_raw.split(",") if p.strip()]
        else:
            paths = list(paths_raw) if isinstance(paths_raw, list) else []

        hooks = frontmatter.get("hooks", {})
        if not isinstance(hooks, dict):
            hooks = {}

        description = str(frontmatter.get("description", ""))
        agent = str(frontmatter.get("agent", ""))
        effort = int(frontmatter.get("effort", 3))
        enabled = bool(frontmatter.get("enabled", True))

        return SkillDef(
            name=name,
            description=description,
            allowed_tools=allowed_tools,
            paths=paths,
            hooks=hooks,
            agent=agent,
            effort=effort,
            body=body,
            file_path=str(md_path.resolve()),
            enabled=enabled,
        )


# ------------------------------------------------------------------
# Module-level convenience: a singleton loader + thin wrappers
# ------------------------------------------------------------------

_loader: Optional[SkillsLoader] = None


def _get_loader() -> SkillsLoader:
    global _loader  # noqa: PLW0603
    if _loader is None:
        _loader = SkillsLoader()
    return _loader


def find_skills(base_dir: str | None = None, scope: str = "global") -> list[SkillDef]:
    """Module-level shortcut for :meth:`SkillsLoader.find_skills`."""
    return _get_loader().find_skills(base_dir, scope=scope)


def match_skills(skills: list[SkillDef], current_path: str) -> list[SkillDef]:
    """Module-level shortcut for :meth:`SkillsLoader.match_skills`."""
    return _get_loader().match_skills(skills, current_path)


def format_skills_for_prompt(skills: list[SkillDef]) -> str:
    """Module-level shortcut for :meth:`SkillsLoader.format_skills_for_prompt`."""
    return _get_loader().format_skills_for_prompt(skills)
