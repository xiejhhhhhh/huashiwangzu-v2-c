import json
from pathlib import Path

from dev_toolkit.user_profile_tools import audit_profile, get_profile, suggest_profile, update_profile


def _load(text: str) -> dict:
    return json.loads(text)


def test_user_profile_suggest_records_candidate(tmp_path: Path) -> None:
    profile_path = tmp_path / "backend" / "logs" / "user_profile" / "profile.json"

    result = _load(suggest_profile(
        tmp_path,
        profile_path,
        observation="用户长期偏好：Agent 开发要先规划再执行，并且文档不要写流水账。",
        user="default",
        source="test",
        agent="pytest",
        evidence_count=2,
        explicit=True,
        auto_record=True,
    ))

    assert result["success"] is True
    assert result["should_record"] is True
    assert result["requires_confirmation"] is True
    assert result["candidate"]["status"] == "candidate"
    assert profile_path.exists()

    profile = _load(get_profile(tmp_path, profile_path, user="default"))
    assert profile["candidate_count"] == 1
    assert profile["preferences"] == []


def test_user_profile_confirm_candidate_requires_confirm(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    suggested = _load(suggest_profile(
        tmp_path,
        profile_path,
        observation="用户以后喜欢明确判断，不要过度说不足。",
        user="default",
        source="test",
        agent="pytest",
        evidence_count=3,
        explicit=True,
        auto_record=True,
    ))
    candidate_id = suggested["candidate"]["id"]

    rejected = _load(update_profile(tmp_path, profile_path, {
        "action": "confirm_candidate",
        "id": candidate_id,
        "user": "default",
    }))
    assert rejected["success"] is False
    assert "CONFIRM" in rejected["error"]

    confirmed = _load(update_profile(tmp_path, profile_path, {
        "action": "confirm_candidate",
        "id": candidate_id,
        "user": "default",
        "confirm": "CONFIRM",
    }))
    assert confirmed["success"] is True
    assert confirmed["item"]["status"] == "confirmed"

    profile = _load(get_profile(tmp_path, profile_path, user="default"))
    assert profile["preferences"] or profile["habits"] or profile["taboos"]


def test_user_profile_audit_flags_raw_profile_in_docs(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    docs_dir = tmp_path / "开发文档"
    docs_dir.mkdir()
    (docs_dir / "README.md").write_text(
        '{"schema_version": 1, "profiles": {"default": {"candidates": []}}}',
        encoding="utf-8",
    )

    result = _load(audit_profile(tmp_path, profile_path, user="default", scan_docs=True))

    assert result["success"] is False
    assert any(item["kind"] == "raw_profile_record_in_docs" for item in result["issues"])


def test_user_profile_upsert_and_deactivate(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    upserted = _load(update_profile(tmp_path, profile_path, {
        "action": "upsert_taboo",
        "confirm": "CONFIRM",
        "text": "不要把原始用户画像记录复制到开发文档。",
        "user": "default",
    }))
    assert upserted["success"] is True
    item_id = upserted["item"]["id"]

    deactivated = _load(update_profile(tmp_path, profile_path, {
        "action": "deactivate",
        "confirm": "CONFIRM",
        "bucket": "taboos",
        "id": item_id,
        "user": "default",
    }))
    assert deactivated["success"] is True

    profile = _load(get_profile(tmp_path, profile_path, user="default"))
    assert profile["taboos"] == []
