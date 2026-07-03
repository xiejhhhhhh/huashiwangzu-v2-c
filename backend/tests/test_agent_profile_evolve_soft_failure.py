"""Profile evolve should soft-fail when the LLM response is not usable."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.agent.backend.services import profile_evolve


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self):
        self.profile = SimpleNamespace(
            owner_id=4,
            profile_data={},
            version=1,
            evolved_at=None,
        )
        self.rows = [
            (11, "user", "请记住我喜欢明确的边界。"),
            (12, "assistant", "好的。"),
        ]
        self.execute_calls = 0
        self.added = []
        self.commits = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _ScalarResult(self.profile)
        if self.execute_calls == 2:
            return _ScalarResult(None)
        if self.execute_calls == 3:
            return _RowsResult(self.rows)
        return _ScalarResult(None)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commits += 1


class _FakeSessionFactory:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc_info):
        return None


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "empty_llm_response"),
        ("我觉得用户比较直接，但这里不是 JSON", "unparseable_llm_profile_json"),
    ],
)
@pytest.mark.asyncio
async def test_profile_evolve_llm_soft_failures_are_skipped(monkeypatch, content, reason) -> None:
    db = _FakeDb()

    async def fake_chat(**_kwargs):
        return {"content": content}

    monkeypatch.setattr(profile_evolve, "AsyncSessionLocal", _FakeSessionFactory(db))
    monkeypatch.setattr(profile_evolve.gateway_router, "chat", fake_chat)

    result = await profile_evolve.handle_profile_evolve({
        "conversation_id": 7,
        "owner_id": 4,
    })

    assert result["status"] == "failed"
    assert result["error"] == reason
    assert result.get("retryable") is True
    assert db.profile.profile_data == {}
    assert db.profile.version == 1
    assert db.commits == 0
    assert len(db.added) == 0


def test_parse_profile_json_accepts_fenced_and_python_style_dict() -> None:
    parsed = profile_evolve._parse_profile_json(
        "```json\n{'tone': '直接', 'taboos': '废话', 'focus': ['架构'], 'habits': []}\n```"
    )

    assert parsed == {
        "tone": "直接",
        "taboos": ["废话"],
        "focus": ["架构"],
        "habits": [],
    }
