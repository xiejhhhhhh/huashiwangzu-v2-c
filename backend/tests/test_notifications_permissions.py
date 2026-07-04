import pytest
from app.database import AsyncSessionLocal
from app.main import app
from app.models.system import Notification, UserNotificationRead
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
        notification_ids = (
            await db.execute(
                select(Notification.id).where(Notification.title.like(f"test_notification_{marker}%"))
            )
        ).scalars().all()
        if notification_ids:
            await db.execute(
                delete(UserNotificationRead).where(
                    UserNotificationRead.notification_id.in_(notification_ids)
                )
            )
        await db.execute(
            delete(Notification).where(Notification.title.like(f"test_notification_{marker}%"))
        )
        await db.commit()


@pytest.mark.asyncio
async def test_module_notification_requires_admin() -> None:
    marker = "module_permission"
    editor = await _user("editor")
    admin = await _user("admin")
    await _cleanup(marker)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/notifications/module",
                json={
                    "title": f"test_notification_{marker}_editor",
                    "content": "should be rejected",
                    "notification_type": "info",
                },
                headers=_headers(editor),
            )
            assert response.status_code == 403
            assert response.json()["success"] is False

            response = await client.post(
                "/api/notifications/module",
                json={
                    "title": f"test_notification_{marker}_admin",
                    "content": "allowed",
                    "notification_type": "info",
                },
                headers=_headers(admin),
            )
            assert response.status_code == 200
            assert response.json()["data"]["id"] > 0
    finally:
        await _cleanup(marker)
