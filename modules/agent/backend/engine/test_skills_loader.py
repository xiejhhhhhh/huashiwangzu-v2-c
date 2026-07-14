"""Tests for skills_loader.py — priority resolution + skill discovery."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ..services.skill_governance_service import list_active_skill_defs
from .context_pipeline import _inject_skills
from .skills_loader import SkillDef, resolve_skill_priority


class TestResolveSkillPriority:
    def test_empty_list(self):
        assert resolve_skill_priority([]) == []

    def test_no_duplicates_returns_all(self):
        skills = [
            SkillDef(name="skill_a", scope="global"),
            SkillDef(name="skill_b", scope="workspace"),
        ]
        result = resolve_skill_priority(skills)
        assert len(result) == 2

    def test_workspace_beats_global(self):
        skills = [
            SkillDef(name="same_name", scope="global", priority=0),
            SkillDef(name="same_name", scope="workspace", priority=0),
        ]
        result = resolve_skill_priority(skills)
        assert len(result) == 1
        assert result[0].scope == "workspace"

    def test_project_beats_global(self):
        skills = [
            SkillDef(name="same_name", scope="global", priority=5),
            SkillDef(name="same_name", scope="project", priority=0),
        ]
        result = resolve_skill_priority(skills)
        assert len(result) == 1
        assert result[0].scope == "project"

    def test_priority_tiebreak_within_same_scope(self):
        skills = [
            SkillDef(name="same_name", scope="workspace", priority=1),
            SkillDef(name="same_name", scope="workspace", priority=10),
        ]
        result = resolve_skill_priority(skills)
        assert len(result) == 1
        assert result[0].priority == 10

    def test_three_scopes(self):
        skills = [
            SkillDef(name="dup", scope="global", priority=0),
            SkillDef(name="dup", scope="project", priority=0),
            SkillDef(name="dup", scope="workspace", priority=0),
        ]
        result = resolve_skill_priority(skills)
        assert len(result) == 1
        assert result[0].scope == "workspace"

    def test_multiple_names_preserved(self):
        skills = [
            SkillDef(name="a", scope="global"),
            SkillDef(name="a", scope="workspace"),
            SkillDef(name="b", scope="global"),
            SkillDef(name="c", scope="project"),
        ]
        result = resolve_skill_priority(skills)
        assert len(result) == 3
        names = {s.name for s in result}
        assert names == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_active_skill_defs_drive_prompt_injection() -> None:
    item = SimpleNamespace(
        name="file-analysis",
        description="文件分析",
        allowed_tools=["desktop-tools__read_file"],
        paths=[],
        body="按步骤分析文件。",
        enabled=True,
        scope="global",
        priority=10,
    )
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = [item]
    db = AsyncMock()
    db.execute.return_value = scalar_result

    skills = await list_active_skill_defs(db)
    prompt = await _inject_skills(db, "系统提示")

    assert [skill.name for skill in skills] == ["file-analysis"]
    assert '<skill name="file-analysis">' in prompt
    assert "按步骤分析文件。" in prompt
