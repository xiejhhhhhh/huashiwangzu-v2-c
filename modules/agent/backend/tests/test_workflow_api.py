from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from app.database import AsyncSessionLocal
from app.main import app
from app.models.user import User
from app.services.auth import create_access_token
from app.services.module_registry import call_capability
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.agent.backend.handlers import workflow as workflow_handler  # noqa: F401
from modules.agent.backend.init_db import run_init
from modules.agent.backend.models import ApprovalQueue
from modules.agent.backend.services import workflow_service as svc
from modules.agent.backend.workflow_models import (
    AgentFailureRecord,
    AgentToolCall,
    AgentVerificationResult,
    AgentWorkflowArtifact,
    AgentWorkflowRun,
    AgentWorkflowStep,
)


@pytest_asyncio.fixture(scope="module", autouse=True)
async def ensure_workflow_schema() -> None:
    async with AsyncSessionLocal() as session:
        await run_init(session)


@pytest_asyncio.fixture()
async def db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture()
async def cleanup_runs(db: AsyncSession) -> AsyncIterator[list[int]]:
    run_ids: list[int] = []
    try:
        yield run_ids
    finally:
        if run_ids:
            await db.execute(delete(ApprovalQueue).where(ApprovalQueue.workflow_run_id.in_(run_ids)))
            await db.execute(delete(AgentFailureRecord).where(AgentFailureRecord.run_id.in_(run_ids)))
            await db.execute(delete(AgentVerificationResult).where(AgentVerificationResult.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowArtifact).where(AgentWorkflowArtifact.run_id.in_(run_ids)))
            await db.execute(delete(AgentToolCall).where(AgentToolCall.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowStep).where(AgentWorkflowStep.run_id.in_(run_ids)))
            await db.execute(delete(AgentWorkflowRun).where(AgentWorkflowRun.id.in_(run_ids)))
            await db.commit()


async def _track_run_id(db: AsyncSession, cleanup_runs: list[int], title: str) -> int:
    row = await db.scalar(select(AgentWorkflowRun).where(AgentWorkflowRun.title == title))
    assert row is not None
    cleanup_runs.append(row.id)
    return row.id


async def _user(username: str) -> User:
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == username))
        assert user is not None
        return user


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role, user.session_version)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_workflow_capability_create_record_verification_finalize(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    title = f"capability workflow {uuid4().hex}"
    created = await call_capability(
        "agent",
        "create_workflow",
        {
            "title": title,
            "intent": "capability contract",
            "source": "manual",
            "extra_meta": {"test_marker": "workflow_api"},
        },
        caller="user:711",
        caller_role="viewer",
    )
    run_id = int(created["workflow_run_id"])
    cleanup_runs.append(run_id)
    assert created["status"] == "waiting"

    status = await call_capability(
        "agent",
        "get_workflow_status",
        {"run_id": run_id},
        caller="user:711",
        caller_role="viewer",
    )
    assert status["id"] == run_id
    assert status["status"] == "waiting"
    assert status["needs_confirmation"] is False

    verification = await call_capability(
        "agent",
        "record_verification",
        {
            "run_id": run_id,
            "verification_type": "release_gate",
            "status": "debt",
            "summary": "PASS_WITH_DEBT: skip-ui used",
            "is_required_for_completion": True,
        },
        caller="user:711",
        caller_role="viewer",
    )
    assert verification["verification"]["status"] == "debt"

    finalized = await call_capability(
        "agent",
        "finalize_workflow",
        {"run_id": run_id},
        caller="user:711",
        caller_role="viewer",
    )
    assert finalized["status"] == "partial"
    assert finalized["terminal_status"] == "completed_with_debt"


@pytest.mark.asyncio
async def test_workflow_capability_owner_isolation(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    title = f"owner isolation {uuid4().hex}"
    created = await call_capability(
        "agent",
        "create_workflow",
        {"title": title, "intent": "owner only", "source": "manual"},
        caller="user:721",
        caller_role="viewer",
    )
    cleanup_runs.append(int(created["workflow_run_id"]))

    with pytest.raises(Exception) as exc_info:
        await call_capability(
            "agent",
            "get_workflow_status",
            {"run_id": created["workflow_run_id"]},
            caller="user:722",
            caller_role="viewer",
        )
    assert "not visible" in str(exc_info.value)


@pytest.mark.asyncio
async def test_workflow_capability_ignores_viewer_owner_override(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    created = await call_capability(
        "agent",
        "create_workflow",
        {
            "title": f"owner override {uuid4().hex}",
            "intent": "viewer cannot create for another owner",
            "source": "manual",
            "owner_id": 742,
        },
        caller="user:741",
        caller_role="viewer",
    )
    run_id = int(created["workflow_run_id"])
    cleanup_runs.append(run_id)

    run = await svc.get_workflow(db, run_id, user_id=741)
    assert run.owner_id == 741
    with pytest.raises(Exception) as exc_info:
        await svc.get_workflow(db, run_id, user_id=742)
    assert "not visible" in str(exc_info.value)


@pytest.mark.asyncio
async def test_workflow_capability_admin_can_list_all_owners(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    admin = await _user("admin")
    first = await svc.create_workflow(
        db,
        title=f"admin list first {uuid4().hex}",
        intent="admin capability list",
        source="manual",
        owner_id=751,
        creator_id=751,
    )
    second = await svc.create_workflow(
        db,
        title=f"admin list second {uuid4().hex}",
        intent="admin capability list",
        source="manual",
        owner_id=752,
        creator_id=752,
    )
    cleanup_runs.extend([first.id, second.id])

    listed = await call_capability(
        "agent",
        "list_workflows",
        {"limit": 100},
        caller=f"user:{admin.id}",
        caller_role="admin",
    )
    listed_ids = {item["id"] for item in listed["items"]}
    assert first.id in listed_ids
    assert second.id in listed_ids
    listed_items = {item["id"]: item for item in listed["items"]}
    assert listed_items[first.id]["owner_id"] == 751


@pytest.mark.asyncio
async def test_workflow_http_routes_create_verify_and_finalize(
    cleanup_runs: list[int],
) -> None:
    admin = await _user("admin")
    title = f"http workflow {uuid4().hex}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/workflows",
            json={"title": title, "intent": "http route contract", "source": "manual"},
            headers=_headers(admin),
        )
        assert response.status_code == 200
        created = response.json()["data"]
        run_id = int(created["workflow_run_id"])
        cleanup_runs.append(run_id)
        assert created["status"] == "waiting"

        response = await client.get(f"/api/agent/workflows/{run_id}", headers=_headers(admin))
        assert response.status_code == 200
        detail = response.json()["data"]
        assert detail["id"] == run_id
        assert detail["status"] == "waiting"
        assert "tool_calls" in detail

        response = await client.get(f"/api/agent/workflows/{run_id}/multi-agent-summary", headers=_headers(admin))
        assert response.status_code == 200
        summary = response.json()["data"]
        assert summary == {"items": [], "total": 0}

        response = await client.post(
            f"/api/agent/workflows/{run_id}/verifications",
            json={
                "verification_type": "manual_review",
                "status": "pass",
                "summary": "HTTP route verification passed",
                "is_required_for_completion": True,
            },
            headers=_headers(admin),
        )
        assert response.status_code == 200
        assert response.json()["data"]["verification"]["status"] == "pass"

        response = await client.post(
            f"/api/agent/workflows/{run_id}/finalize",
            json={"developer_summary": "HTTP route finalized"},
            headers=_headers(admin),
        )
        assert response.status_code == 200
        finalized = response.json()["data"]
        assert finalized["status"] == "completed"
        assert finalized["terminal_status"] == "clean_completed"


@pytest.mark.asyncio
async def test_workflow_demo_seed_admin_only_and_cleanup() -> None:
    admin = await _user("admin")
    viewer = await _user("viewer")
    marker = f"agent-demo-workflow-{uuid4().hex}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/workflows/demo-seed",
            json={"marker": marker},
            headers=_headers(viewer),
        )
        assert response.status_code == 403

        response = await client.post(
            "/api/agent/workflows/demo-seed",
            json={"marker": marker, "cleanup_existing": True},
            headers=_headers(admin),
        )
        assert response.status_code == 200
        seeded = response.json()["data"]
        assert seeded["count"] == 4

        response = await client.get(
            "/api/agent/workflows?has_artifacts=true&limit=100",
            headers=_headers(admin),
        )
        assert response.status_code == 200
        artifact_items = response.json()["data"]["items"]
        assert any(item["title"].startswith(marker) and item["artifact_count"] > 0 for item in artifact_items)

        response = await client.get(
            "/api/agent/workflows?has_failures=true&limit=100",
            headers=_headers(admin),
        )
        assert response.status_code == 200
        failure_items = response.json()["data"]["items"]
        assert any(item["title"].startswith(marker) and item["failure_count"] > 0 for item in failure_items)

        failed_run_id = next(item["id"] for item in failure_items if item["title"].startswith(marker))
        response = await client.get(f"/api/agent/workflows/{failed_run_id}", headers=_headers(admin))
        assert response.status_code == 200
        detail = response.json()["data"]
        assert detail["failures"]
        assert detail["failures"][0]["failure_type"] == "semantic_failure"
        assert "语义失败" in detail["failures"][0]["handoff_note"]

        response = await client.get("/api/agent/workflows/governance-summary", headers=_headers(admin))
        assert response.status_code == 200
        summary = response.json()["data"]
        assert summary["total"] >= 4
        assert any(item["failure_type"] == "semantic_failure" for item in summary["recent_errors"])

        response = await client.post(
            "/api/agent/workflows/demo-seed/cleanup",
            json={"marker": marker},
            headers=_headers(admin),
        )
        assert response.status_code == 200
        assert response.json()["data"]["deleted"] == 4

        response = await client.get(
            "/api/agent/workflows?has_references=true&limit=100",
            headers=_headers(admin),
        )
        assert response.status_code == 200
        remaining = response.json()["data"]["items"]
        assert all(not item["title"].startswith(marker) for item in remaining)


@pytest.mark.asyncio
async def test_created_capability_run_is_queryable_from_service(
    db: AsyncSession,
    cleanup_runs: list[int],
) -> None:
    title = f"service query {uuid4().hex}"
    await call_capability(
        "agent",
        "create_workflow",
        {"title": title, "intent": "service query", "source": "manual"},
        caller="user:731",
        caller_role="viewer",
    )
    run_id = await _track_run_id(db, cleanup_runs, title)
    run = await svc.get_workflow(db, run_id, user_id=731)
    assert run.title == title
    assert run.status == "waiting"
