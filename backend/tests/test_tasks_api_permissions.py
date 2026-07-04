import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.database import AsyncSessionLocal
from app.main import app
from app.models.system import SystemTaskQueue
from app.models.user import User
from app.services.auth import create_access_token
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select


async def _user(username: str) -> User:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))
        assert user is not None
        return user


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role, user.session_version)
    return {"Authorization": f"Bearer {token}"}


async def _cleanup(marker: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(SystemTaskQueue).where(
                SystemTaskQueue.task_type.like(f"test_task_api_{marker}%")
            )
        )
        await db.commit()


async def _create_task(
    marker: str,
    creator_id: int,
    *,
    status: str = "failed",
    retry_count: int = 2,
    error_message: str | None = "boom",
    result: dict | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> int:
    async with AsyncSessionLocal() as db:
        task = SystemTaskQueue(
            task_type=f"test_task_api_{marker}",
            module="test",
            parameters=json.dumps({"marker": marker}),
            status=status,
            priority=0,
            creator_id=creator_id,
            retry_count=retry_count,
            error_message=error_message,
            result=json.dumps(result, ensure_ascii=False) if result is not None else None,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(task)
        await db.commit()
        return task.id


async def _get_task(task_id: int) -> SystemTaskQueue:
    async with AsyncSessionLocal() as db:
        task = await db.get(SystemTaskQueue, task_id)
        assert task is not None
        return task


def _assert_permission_denied(response) -> None:
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["data"] is None
    assert data["error"]


@pytest.mark.asyncio
async def test_non_admin_task_api_is_limited_to_own_tasks() -> None:
    marker = uuid4().hex
    admin = await _user("admin")
    editor = await _user("editor")
    await _cleanup(marker)
    try:
        editor_task_id = await _create_task(f"{marker}_editor", editor.id)
        admin_task_id = await _create_task(f"{marker}_admin", admin.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            editor_headers = _headers(editor)

            response = await client.get("/api/tasks/", headers=editor_headers)
            assert response.status_code == 200
            listed_ids = {item["id"] for item in response.json()["data"]}
            assert editor_task_id in listed_ids
            assert admin_task_id not in listed_ids

            response = await client.get(f"/api/tasks/{admin_task_id}", headers=editor_headers)
            _assert_permission_denied(response)

            response = await client.post(
                f"/api/tasks/{admin_task_id}/cancel",
                headers=editor_headers,
            )
            _assert_permission_denied(response)

            response = await client.post(
                f"/api/tasks/{admin_task_id}/retry",
                headers=editor_headers,
            )
            _assert_permission_denied(response)

            protected_task = await _get_task(admin_task_id)
            assert protected_task.status == "failed"
            assert protected_task.retry_count == 2
            assert protected_task.error_message == "boom"

            response = await client.post(
                f"/api/tasks/{editor_task_id}/retry",
                headers=editor_headers,
            )
            assert response.status_code == 200
            response = await client.post(
                f"/api/tasks/{editor_task_id}/cancel",
                headers=editor_headers,
            )
            assert response.status_code == 200
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_non_admin_cannot_submit_arbitrary_task_type() -> None:
    marker = uuid4().hex
    editor = await _user("editor")
    await _cleanup(marker)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/tasks/submit",
                json={
                    "module": "test",
                    "task_type": f"test_task_api_{marker}_submitted",
                    "parameters": {"marker": marker},
                },
                headers=_headers(editor),
            )
            _assert_permission_denied(response)

        async with AsyncSessionLocal() as db:
            count = len(
                (
                    await db.execute(
                        select(SystemTaskQueue).where(
                            SystemTaskQueue.task_type.like(f"test_task_api_{marker}%")
                        )
                    )
                ).scalars().all()
            )
        assert count == 0
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_admin_can_submit_and_manage_any_task() -> None:
    marker = uuid4().hex
    admin = await _user("admin")
    editor = await _user("editor")
    await _cleanup(marker)
    try:
        editor_task_id = await _create_task(f"{marker}_editor", editor.id)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            admin_headers = _headers(admin)

            response = await client.post(
                "/api/tasks/submit",
                json={
                    "module": "test",
                    "task_type": f"test_task_api_{marker}_submitted",
                    "parameters": {"marker": marker},
                },
                headers=admin_headers,
            )
            assert response.status_code == 200
            submitted_id = response.json()["data"]["id"]

            response = await client.get(f"/api/tasks/{editor_task_id}", headers=admin_headers)
            assert response.status_code == 200
            assert response.json()["data"]["id"] == editor_task_id

            response = await client.post(
                f"/api/tasks/{editor_task_id}/retry",
                headers=admin_headers,
            )
            assert response.status_code == 200

            response = await client.post(
                f"/api/tasks/{editor_task_id}/cancel",
                headers=admin_headers,
            )
            assert response.status_code == 200

            response = await client.get("/api/tasks/", headers=admin_headers)
            assert response.status_code == 200
            listed_ids = {item["id"] for item in response.json()["data"]}
            assert editor_task_id in listed_ids
            assert submitted_id in listed_ids
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_retry_only_accepts_failed_tasks_and_clears_previous_result() -> None:
    marker = uuid4().hex
    admin = await _user("admin")
    await _cleanup(marker)
    try:
        failed_task_id = await _create_task(
            f"{marker}_failed",
            admin.id,
            status="failed",
            retry_count=3,
            error_message="old failure",
            result={"success": False, "error": "old failure"},
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        completed_task_id = await _create_task(
            f"{marker}_completed",
            admin.id,
            status="completed",
            error_message=None,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            admin_headers = _headers(admin)

            response = await client.post(
                f"/api/tasks/{completed_task_id}/retry",
                headers=admin_headers,
            )
            assert response.status_code == 422

            response = await client.post(
                f"/api/tasks/{failed_task_id}/retry",
                headers=admin_headers,
            )
            assert response.status_code == 200

        retried = await _get_task(failed_task_id)
        assert retried.status == "pending"
        assert retried.retry_count == 0
        assert retried.error_message is None
        assert retried.result is None
        assert retried.started_at is None
        assert retried.completed_at is None
    finally:
        await _cleanup(marker)


@pytest.mark.asyncio
async def test_cancel_only_accepts_pending_or_running_tasks() -> None:
    marker = uuid4().hex
    admin = await _user("admin")
    await _cleanup(marker)
    try:
        failed_task_id = await _create_task(f"{marker}_failed", admin.id, status="failed")
        completed_task_id = await _create_task(
            f"{marker}_completed",
            admin.id,
            status="completed",
            error_message=None,
        )
        pending_task_id = await _create_task(
            f"{marker}_pending",
            admin.id,
            status="pending",
            error_message=None,
        )
        running_task_id = await _create_task(
            f"{marker}_running",
            admin.id,
            status="running",
            error_message=None,
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            admin_headers = _headers(admin)

            for task_id in (failed_task_id, completed_task_id):
                response = await client.post(
                    f"/api/tasks/{task_id}/cancel",
                    headers=admin_headers,
                )
                assert response.status_code == 422

            for task_id in (pending_task_id, running_task_id):
                response = await client.post(
                    f"/api/tasks/{task_id}/cancel",
                    headers=admin_headers,
                )
                assert response.status_code == 200

        for task_id in (pending_task_id, running_task_id):
            cancelled = await _get_task(task_id)
            assert cancelled.status == "failed"
            assert cancelled.error_message == "Manually cancelled"
            assert cancelled.completed_at is not None
    finally:
        await _cleanup(marker)
