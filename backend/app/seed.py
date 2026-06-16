"""Initial data seeder. Run once after alembic upgrade head.

Usage:
    python -m app.seed
"""

import asyncio
import json
import os
from pathlib import Path
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.app import App
from app.models.role_matrix import RoleMatrix
from app.services.auth import hash_password

APPS_DATA = json.loads((Path(__file__).parent / "seed_data" / "apps.json").read_text(encoding="utf-8"))
DEFAULT_PASSWORD = os.getenv("V2_SEED_DEFAULT_PASSWORD", "")


def _seed_password() -> str:
    if DEFAULT_PASSWORD:
        return DEFAULT_PASSWORD
    raise RuntimeError("V2_SEED_DEFAULT_PASSWORD is required for seeding")


async def seed():
    async with AsyncSessionLocal() as db:
        # ── Users ──
        result = await db.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                password_hash=hash_password(_seed_password()),
                display_name="Administrator",
                email="admin@huashiwangzu.com",
                role="admin",
                enabled=True,
            )
            db.add(admin)

        result = await db.execute(select(User).where(User.username == "viewer"))
        if not result.scalar_one_or_none():
            viewer = User(
                username="viewer",
                password_hash=hash_password(_seed_password()),
                display_name="Viewer",
                email="viewer@huashiwangzu.com",
                role="viewer",
                enabled=True,
            )
            db.add(viewer)

        result = await db.execute(select(User).where(User.username == "editor"))
        if not result.scalar_one_or_none():
            editor = User(
                username="editor",
                password_hash=hash_password(_seed_password()),
                display_name="Editor",
                email="editor@huashiwangzu.com",
                role="editor",
                enabled=True,
            )
            db.add(editor)

        await db.commit()
        print("✅ Users seeded")

        # ── Desktop Apps (32 modules) ──
        apps_data = APPS_DATA

        for app_data in apps_data:
            result = await db.execute(select(App).where(App.key == app_data["key"]))
            if not result.scalar_one_or_none():
                db.add(App(**app_data))

        await db.commit()
        print(f"✅ {len(apps_data)} apps seeded")

        # ── Role matrix ──
        result = await db.execute(select(RoleMatrix))
        if not result.scalar_one_or_none():
            defaults = [
                RoleMatrix(role_key="admin", display_name="管理员", permissions={"user_management": True, "system_config": True, "role_matrix": True}),
                RoleMatrix(role_key="editor", display_name="编辑者", permissions={"user_management": False, "system_config": False, "role_matrix": False}),
                RoleMatrix(role_key="viewer", display_name="查看者", permissions={"user_management": False, "system_config": False, "role_matrix": False}),
            ]
            for row in defaults:
                db.add(row)
            await db.commit()
            print("✅ Role matrix seeded")

    await db.close()


if __name__ == "__main__":
    asyncio.run(seed())
