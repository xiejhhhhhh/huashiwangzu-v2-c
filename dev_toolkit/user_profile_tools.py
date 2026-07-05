"""Runtime user profile and preference tools for the project toolkit MCP server."""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

TOOL_NAMES = {
    "user_profile_get",
    "user_profile_suggest",
    "user_profile_update",
    "user_profile_audit",
}
SCHEMA_VERSION = 1
MAX_HISTORY = 200
LIMITS = {
    "preferences": 30,
    "habits": 20,
    "taboos": 15,
    "candidates": 50,
}
WRITE_ACTIONS = {
    "confirm_candidate",
    "reject_candidate",
    "upsert_preference",
    "upsert_habit",
    "upsert_taboo",
    "deactivate",
}


class ProfileReadError(RuntimeError):
    """Raised when a profile file exists but cannot be decoded."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", "-", value.strip()).strip("-")
    return cleaned[:80] or "preference"


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def empty_profile() -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "profiles": {
            "default": {
                "preferences": [],
                "habits": [],
                "taboos": [],
                "candidates": [],
                "history": [],
            }
        },
    }


def _empty_user() -> dict[str, Any]:
    return {
        "preferences": [],
        "habits": [],
        "taboos": [],
        "candidates": [],
        "history": [],
    }


def _normalize_item(item: Any, *, default_status: str = "confirmed") -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or item.get("value") or "").strip()
    if not text:
        return None
    now = _now()
    normalized = {
        "id": str(item.get("id") or _slug(text[:60])),
        "category": str(item.get("category") or "general"),
        "text": text,
        "status": str(item.get("status") or default_status),
        "confidence": float(item.get("confidence") or 0.5),
        "evidence_count": int(item.get("evidence_count") or 1),
        "source": str(item.get("source") or "manual"),
        "agent": str(item.get("agent") or ""),
        "created_at": str(item.get("created_at") or now),
        "updated_at": str(item.get("updated_at") or now),
    }
    for key in ("note", "score", "requires_confirmation"):
        if key in item:
            normalized[key] = item[key]
    return normalized


def _normalize_user(raw: Any) -> dict[str, Any]:
    user = _empty_user()
    if not isinstance(raw, dict):
        return user
    for bucket in ("preferences", "habits", "taboos"):
        values = raw.get(bucket) if isinstance(raw.get(bucket), list) else []
        user[bucket] = [item for item in (_normalize_item(value) for value in values) if item]
    values = raw.get("candidates") if isinstance(raw.get("candidates"), list) else []
    user["candidates"] = [
        item for item in (_normalize_item(value, default_status="candidate") for value in values) if item
    ]
    history = raw.get("history") if isinstance(raw.get("history"), list) else []
    user["history"] = [entry for entry in history if isinstance(entry, dict)][-MAX_HISTORY:]
    return user


def normalize_profile(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return empty_profile()
    profile = empty_profile()
    profile.update({key: value for key, value in data.items() if key != "profiles"})
    profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    normalized = {str(user or "default"): _normalize_user(raw) for user, raw in profiles.items()}
    if "default" not in normalized:
        normalized["default"] = _empty_user()
    profile["profiles"] = normalized
    profile["schema_version"] = SCHEMA_VERSION
    profile.setdefault("created_at", _now())
    profile.setdefault("updated_at", _now())
    return profile


def read_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_profile()
    try:
        return normalize_profile(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileReadError(f"Failed to read user profile {path}: {exc}") from exc


def _backup_corrupt_profile(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.name}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    path.replace(backup)
    return backup


def write_profile(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["schema_version"] = SCHEMA_VERSION
    data["updated_at"] = _now()
    for user_data in data.get("profiles", {}).values():
        if isinstance(user_data, dict):
            user_data["history"] = list(user_data.get("history", []))[-MAX_HISTORY:]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


@contextmanager
def locked_profile(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        recovered_from = None
        try:
            try:
                profile = read_profile(path)
            except ProfileReadError:
                recovered_from = _backup_corrupt_profile(path)
                profile = empty_profile()
                if recovered_from:
                    profile["recovered_from_corrupt"] = str(recovered_from)
            yield profile
            write_profile(path, profile)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _user_profile(profile: dict[str, Any], user: str) -> dict[str, Any]:
    profiles = profile.setdefault("profiles", {})
    return profiles.setdefault(user or "default", _empty_user())


def _history(user_data: dict[str, Any], action: str, detail: dict[str, Any]) -> None:
    history = user_data.setdefault("history", [])
    history.append({"at": _now(), "action": action, "detail": detail})
    user_data["history"] = history[-MAX_HISTORY:]


def _visible(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("status") != "inactive"]


def _compact(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "category",
        "text",
        "status",
        "confidence",
        "evidence_count",
        "source",
        "updated_at",
        "score",
        "requires_confirmation",
    )
    return {key: item.get(key) for key in keys if key in item}


def _category(text: str) -> str:
    lower = text.lower()
    if any(word in text for word in ("禁止", "不能", "不要", "禁忌")):
        return "taboo"
    if any(word in text for word in ("文档", "流水账", "开发文档", "README")) or "docs" in lower:
        return "documentation"
    if any(word in text for word in ("规划", "执行", "收口", "验证", "流程")):
        return "workflow"
    if any(word in text for word in ("明确判断", "反问", "保守", "解释")):
        return "communication"
    if any(word in text for word in ("模块", "框架", "项目", "代码")):
        return "project_operation"
    return "work_style"


def _bucket_for_category(category: str) -> str:
    if category == "taboo":
        return "taboos"
    if category in {"workflow", "work_style"}:
        return "habits"
    return "preferences"


def _bulk_data_risk(text: str) -> float:
    url_count = len(re.findall(r"https?://|www\.", text, flags=re.IGNORECASE))
    list_markers = len(re.findall(r"[,，;；\n]", text))
    digit_groups = len(re.findall(r"\d{4,}", text))
    risk = 0.0
    if url_count:
        risk += min(0.5, url_count * 0.2)
    if list_markers >= 8:
        risk += 0.3
    if digit_groups >= 5:
        risk += 0.2
    if len(text) > 1200:
        risk += 0.3
    return min(risk, 1.0)


def _score_observation(text: str, evidence_count: int, explicit: bool) -> dict[str, Any]:
    clarity = 0.25 if explicit else 0.12
    repetition = min(max(evidence_count, 1), 5) * 0.08
    durable_keywords = ("长期", "以后", "偏好", "喜欢", "不喜欢", "禁止", "必须", "不要", "习惯")
    durability = 0.22 if any(word in text for word in durable_keywords) else 0.1
    impact_keywords = ("Agent", "开发", "文档", "MCP", "验证", "规则", "边界", "收口")
    future_impact = 0.22 if any(word in text for word in impact_keywords) else 0.08
    conflict_risk = 0.15 if "覆盖" in text and "规则" in text else 0.0
    bulk_risk = _bulk_data_risk(text)
    score = max(0.0, min(1.0, clarity + repetition + durability + future_impact - conflict_risk - bulk_risk))
    return {
        "score": round(score, 3),
        "clarity": clarity,
        "repetition": repetition,
        "durability": durability,
        "future_impact": future_impact,
        "conflict_risk": conflict_risk,
        "bulk_data_risk": bulk_risk,
    }


def _find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("id") == item_id:
            return item
    return None


def _find_by_text(items: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    normalized = re.sub(r"\s+", "", text)
    for item in items:
        if re.sub(r"\s+", "", str(item.get("text") or "")) == normalized:
            return item
    return None


def _upsert_item(
    user_data: dict[str, Any],
    bucket: str,
    *,
    text: str,
    category: str,
    confidence: float,
    source: str,
    agent: str,
    item_id: str = "",
) -> dict[str, Any]:
    items = user_data.setdefault(bucket, [])
    final_id = item_id or _slug(f"{category}-{text[:48]}")
    existing = _find_by_id(items, final_id) or _find_by_text(items, text)
    now = _now()
    if existing:
        existing.update({
            "category": category,
            "text": text,
            "status": "confirmed",
            "confidence": max(float(existing.get("confidence") or 0.0), confidence),
            "evidence_count": int(existing.get("evidence_count") or 1) + 1,
            "source": source,
            "agent": agent,
            "updated_at": now,
        })
        return existing
    item = {
        "id": final_id,
        "category": category,
        "text": text,
        "status": "confirmed",
        "confidence": confidence,
        "evidence_count": 1,
        "source": source,
        "agent": agent,
        "created_at": now,
        "updated_at": now,
    }
    items.append(item)
    return item


def _tool_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_definitions() -> list[Any]:
    from mcp.types import Tool

    return [
        Tool(
            name="user_profile_get",
            description="读取运行时用户画像/偏好摘要；只读，不进入开发文档。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {"type": "string", "description": "画像用户 key", "default": "default"},
                    "include_history": {"type": "boolean", "description": "是否返回最近历史", "default": False},
                },
            },
        ),
        Tool(
            name="user_profile_suggest",
            description="根据观察生成候选用户偏好并评分；候选不等于已确认画像。",
            inputSchema={
                "type": "object",
                "properties": {
                    "observation": {"type": "string", "description": "观察到的偏好/习惯/禁忌"},
                    "user": {"type": "string", "default": "default"},
                    "source": {"type": "string", "default": "conversation"},
                    "agent": {"type": "string", "default": ""},
                    "evidence_count": {"type": "number", "default": 1},
                    "explicit": {"type": "boolean", "default": True},
                    "auto_record": {"type": "boolean", "default": True},
                },
                "required": ["observation"],
            },
        ),
        Tool(
            name="user_profile_update",
            description="确认、拒绝、 upsert 或停用用户画像条目；写入操作必须 confirm=CONFIRM。",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "confirm_candidate/reject_candidate/upsert_preference/upsert_habit/upsert_taboo/deactivate",
                    },
                    "confirm": {"type": "string", "description": "写入确认，必须为 CONFIRM"},
                    "user": {"type": "string", "default": "default"},
                    "id": {"type": "string", "description": "候选或条目 id"},
                    "bucket": {"type": "string", "description": "preferences/habits/taboos/candidates"},
                    "text": {"type": "string", "description": "upsert 文本"},
                    "category": {"type": "string", "description": "分类"},
                    "confidence": {"type": "number", "default": 0.9},
                    "source": {"type": "string", "default": "manual"},
                    "agent": {"type": "string", "default": ""},
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="user_profile_audit",
            description="审计用户画像是否膨胀、冲突或含批量原始数据风险。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user": {"type": "string", "default": "default"},
                    "scan_docs": {"type": "boolean", "description": "扫描开发文档原始画像落盘风险", "default": True},
                },
            },
        ),
    ]


def handles_tool(name: str) -> bool:
    return name in TOOL_NAMES


async def handle_tool(repo_root: Path, profile_path: Path, name: str, arguments: dict[str, Any]) -> str:
    user = str(arguments.get("user") or "default").strip() or "default"
    if name == "user_profile_get":
        return get_profile(repo_root, profile_path, user=user, include_history=bool(arguments.get("include_history", False)))
    if name == "user_profile_suggest":
        return suggest_profile(
            repo_root,
            profile_path,
            observation=str(arguments.get("observation") or ""),
            user=user,
            source=str(arguments.get("source") or "conversation"),
            agent=str(arguments.get("agent") or ""),
            evidence_count=int(arguments.get("evidence_count") or 1),
            explicit=bool(arguments.get("explicit", True)),
            auto_record=bool(arguments.get("auto_record", True)),
        )
    if name == "user_profile_update":
        return update_profile(repo_root, profile_path, arguments)
    if name == "user_profile_audit":
        return audit_profile(repo_root, profile_path, user=user, scan_docs=bool(arguments.get("scan_docs", True)))
    raise ValueError(f"未知用户画像工具: {name}")


def get_profile(repo_root: Path, path: Path, *, user: str, include_history: bool = False) -> str:
    try:
        profile = read_profile(path)
    except ProfileReadError as exc:
        return _tool_response({"success": False, "error": str(exc), "rejected": True})
    data = _user_profile(profile, user)
    payload: dict[str, Any] = {
        "success": True,
        "path": _rel(path, repo_root),
        "user": user,
        "preferences": [_compact(item) for item in _visible(data.get("preferences", []))],
        "habits": [_compact(item) for item in _visible(data.get("habits", []))],
        "taboos": [_compact(item) for item in _visible(data.get("taboos", []))],
        "candidate_count": len(_visible(data.get("candidates", []))),
        "recent_candidates": [_compact(item) for item in _visible(data.get("candidates", []))[-10:]],
        "precedence": "current user instructions > system/project rules > confirmed profile > candidates",
        "limits": LIMITS,
    }
    if include_history:
        payload["history"] = data.get("history", [])[-50:]
    return _tool_response(payload)


def suggest_profile(
    repo_root: Path,
    path: Path,
    *,
    observation: str,
    user: str,
    source: str,
    agent: str,
    evidence_count: int,
    explicit: bool,
    auto_record: bool,
) -> str:
    text = observation.strip()
    if not text:
        return _tool_response({"success": False, "error": "observation is required"})
    score_detail = _score_observation(text, evidence_count, explicit)
    should_record = score_detail["score"] >= 0.5
    requires_confirmation = True
    category = _category(text)
    payload: dict[str, Any] = {
        "success": True,
        "should_record": should_record,
        "requires_confirmation": requires_confirmation,
        "score_detail": score_detail,
        "candidate": None,
        "reason": _suggest_reason(score_detail, should_record),
    }
    if not should_record or not auto_record:
        return _tool_response(payload)

    with locked_profile(path) as profile:
        data = _user_profile(profile, user)
        candidates = data.setdefault("candidates", [])
        item_id = _slug(f"{category}-{text[:48]}")
        existing = _find_by_id(candidates, item_id) or _find_by_text(candidates, text)
        now = _now()
        if existing:
            existing["evidence_count"] = int(existing.get("evidence_count") or 1) + max(evidence_count, 1)
            existing["confidence"] = max(float(existing.get("confidence") or 0.0), score_detail["score"])
            existing["updated_at"] = now
            existing["score"] = score_detail["score"]
            existing["requires_confirmation"] = requires_confirmation
            candidate = existing
            action = "update_candidate"
        else:
            candidate = {
                "id": item_id,
                "category": category,
                "text": text,
                "status": "candidate",
                "confidence": score_detail["score"],
                "score": score_detail["score"],
                "evidence_count": max(evidence_count, 1),
                "source": source,
                "agent": agent,
                "created_at": now,
                "updated_at": now,
                "requires_confirmation": requires_confirmation,
            }
            candidates.append(candidate)
            action = "add_candidate"
        _history(data, action, {"id": candidate["id"], "score": candidate.get("score")})
        payload["candidate"] = _compact(candidate)
        payload["path"] = _rel(path, repo_root)
    return _tool_response(payload)


def _suggest_reason(score_detail: dict[str, Any], should_record: bool) -> str:
    if not should_record:
        return "score below threshold; keep it as task-local context, not durable preference"
    if score_detail.get("bulk_data_risk", 0) > 0:
        return "candidate recorded, but raw/bulk data risk should be reviewed before confirmation"
    return "candidate recorded for review; confirmation is required before it becomes an active profile rule"


def update_profile(repo_root: Path, path: Path, arguments: dict[str, Any]) -> str:
    action = str(arguments.get("action") or "").strip()
    if action not in WRITE_ACTIONS:
        return _tool_response({"success": False, "error": f"unsupported action: {action}"})
    if str(arguments.get("confirm") or "") != "CONFIRM":
        return _tool_response({"success": False, "error": "operation requires confirm='CONFIRM'"})

    user = str(arguments.get("user") or "default").strip() or "default"
    item_id = str(arguments.get("id") or "").strip()
    with locked_profile(path) as profile:
        data = _user_profile(profile, user)
        if action == "confirm_candidate":
            candidate = _find_by_id(data.get("candidates", []), item_id)
            if not candidate:
                return _tool_response({"success": False, "error": f"candidate not found: {item_id}"})
            bucket = _bucket_for_category(str(candidate.get("category") or "general"))
            confirmed = _upsert_item(
                data,
                bucket,
                text=str(candidate.get("text") or ""),
                category=str(candidate.get("category") or "general"),
                confidence=float(candidate.get("confidence") or 0.8),
                source=str(candidate.get("source") or "candidate"),
                agent=str(arguments.get("agent") or candidate.get("agent") or ""),
                item_id=str(candidate.get("id") or ""),
            )
            candidate["status"] = "confirmed"
            candidate["updated_at"] = _now()
            _history(data, action, {"id": item_id, "bucket": bucket})
            return _tool_response({"success": True, "action": action, "item": _compact(confirmed), "path": _rel(path, repo_root)})

        if action == "reject_candidate":
            candidate = _find_by_id(data.get("candidates", []), item_id)
            if not candidate:
                return _tool_response({"success": False, "error": f"candidate not found: {item_id}"})
            candidate["status"] = "rejected"
            candidate["updated_at"] = _now()
            _history(data, action, {"id": item_id})
            return _tool_response({"success": True, "action": action, "item": _compact(candidate), "path": _rel(path, repo_root)})

        if action in {"upsert_preference", "upsert_habit", "upsert_taboo"}:
            text = str(arguments.get("text") or "").strip()
            if not text:
                return _tool_response({"success": False, "error": "text is required"})
            bucket = {
                "upsert_preference": "preferences",
                "upsert_habit": "habits",
                "upsert_taboo": "taboos",
            }[action]
            item = _upsert_item(
                data,
                bucket,
                text=text,
                category=str(arguments.get("category") or _category(text)),
                confidence=float(arguments.get("confidence") or 0.9),
                source=str(arguments.get("source") or "manual"),
                agent=str(arguments.get("agent") or ""),
                item_id=item_id,
            )
            _history(data, action, {"id": item["id"], "bucket": bucket})
            return _tool_response({"success": True, "action": action, "item": _compact(item), "path": _rel(path, repo_root)})

        bucket = str(arguments.get("bucket") or "").strip()
        if bucket not in {"preferences", "habits", "taboos", "candidates"}:
            return _tool_response({"success": False, "error": "bucket must be preferences/habits/taboos/candidates"})
        item = _find_by_id(data.get(bucket, []), item_id)
        if not item:
            return _tool_response({"success": False, "error": f"item not found: {bucket}/{item_id}"})
        item["status"] = "inactive"
        item["updated_at"] = _now()
        _history(data, action, {"id": item_id, "bucket": bucket})
        return _tool_response({"success": True, "action": action, "item": _compact(item), "path": _rel(path, repo_root)})


def audit_profile(repo_root: Path, path: Path, *, user: str, scan_docs: bool = True) -> str:
    issues: list[dict[str, Any]] = []
    try:
        profile = read_profile(path)
    except ProfileReadError as exc:
        return _tool_response({"success": False, "error": str(exc), "issues": [{"level": "BLOCKER", "kind": "corrupt_profile"}]})
    data = _user_profile(profile, user)
    counts = {bucket: len(_visible(data.get(bucket, []))) for bucket in LIMITS}
    for bucket, limit in LIMITS.items():
        if counts[bucket] > limit:
            issues.append({"level": "DEBT", "kind": "over_limit", "bucket": bucket, "count": counts[bucket], "limit": limit})
    all_confirmed = data.get("preferences", []) + data.get("habits", []) + data.get("taboos", [])
    seen: dict[str, str] = {}
    for item in all_confirmed:
        text_key = re.sub(r"\s+", "", str(item.get("text") or ""))
        if not text_key or item.get("status") == "inactive":
            continue
        if text_key in seen:
            issues.append({"level": "DEBT", "kind": "duplicate_text", "first_id": seen[text_key], "id": item.get("id")})
        seen[text_key] = str(item.get("id") or "")
        if _bulk_data_risk(str(item.get("text") or "")) >= 0.5:
            issues.append({"level": "DEBT", "kind": "bulk_data_risk", "id": item.get("id")})
    if scan_docs:
        issues.extend(_scan_docs_for_raw_profile(repo_root))
    blocker_count = sum(1 for item in issues if item["level"] == "BLOCKER")
    return _tool_response({
        "success": blocker_count == 0,
        "path": _rel(path, repo_root),
        "user": user,
        "counts": counts,
        "limits": LIMITS,
        "level": "BLOCKER" if blocker_count else "DEBT" if issues else "PASS",
        "issues": issues[:100],
    })


def _scan_docs_for_raw_profile(repo_root: Path) -> list[dict[str, Any]]:
    docs_dir = repo_root / "开发文档"
    if not docs_dir.exists():
        return []
    patterns = (
        "backend/logs/user_profile/profile.json",
        "开发文档/user_profile",
        "开发文档/用户画像",
        '"profiles"',
        '"candidates"',
    )
    issues: list[dict[str, Any]] = []
    for path in docs_dir.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "user_profile" not in text and "用户画像" not in text and '"profiles"' not in text:
            continue
        if any(pattern in text for pattern in patterns) and "schema_version" in text:
            issues.append({"level": "BLOCKER", "kind": "raw_profile_record_in_docs", "path": _rel(path, repo_root)})
    return issues
