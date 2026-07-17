"""ContentAccessPolicyService 骨架（方案07 §21.3 / WP5）。

本轮不做完整 ACL 引擎，只提供统一入口：
- owner 永远可读写
- 非 owner：若绑定 source_file，走文件分享权限
- 草稿（无 source_file）仅 owner

WP7 数据迁移/约束切换不在此。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound, PermissionDenied
from app.models.content import ContentPackage
from app.models.user import User

AccessLevel = Literal["none", "view", "edit", "owner"]


@dataclass
class ContentAccessDecision:
    level: AccessLevel
    can_view: bool
    can_edit: bool
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "canView": self.can_view,
            "canEdit": self.can_edit,
            "reason": self.reason,
        }


async def evaluate_package_access(
    db: AsyncSession,
    *,
    package_id: int,
    user: User | int,
) -> ContentAccessDecision:
    user_id = int(user.id if hasattr(user, "id") else user)
    pkg = await db.get(ContentPackage, package_id)
    if pkg is None or pkg.deleted:
        raise NotFound(f"Package {package_id} not found")

    if pkg.owner_id == user_id:
        return ContentAccessDecision("owner", True, True, "owner")

    # 草稿无物理文件：仅 owner
    if not pkg.source_file_id:
        return ContentAccessDecision("none", False, False, "draft_owner_only")

    try:
        from app.services.file_share_service import check_file_access, check_file_write_access

        access = await check_file_access(db, pkg.source_file_id, user_id)
        if not access.get("accessible"):
            return ContentAccessDecision("none", False, False, "file_not_shared")
        write = await check_file_write_access(db, pkg.source_file_id, user_id)
        if write.get("accessible"):
            return ContentAccessDecision("edit", True, True, "file_share_edit")
        return ContentAccessDecision("view", True, False, "file_share_view")
    except Exception:
        return ContentAccessDecision("none", False, False, "access_check_failed")


async def require_package_view(db: AsyncSession, *, package_id: int, user: User | int) -> ContentPackage:
    decision = await evaluate_package_access(db, package_id=package_id, user=user)
    if not decision.can_view:
        # 不泄露存在性
        raise NotFound(f"Package {package_id} not found")
    pkg = await db.get(ContentPackage, package_id)
    assert pkg is not None
    return pkg


async def require_package_edit(db: AsyncSession, *, package_id: int, user: User | int) -> ContentPackage:
    decision = await evaluate_package_access(db, package_id=package_id, user=user)
    if not decision.can_edit:
        if decision.can_view:
            raise PermissionDenied("Package is read-only for current user")
        raise NotFound(f"Package {package_id} not found")
    pkg = await db.get(ContentPackage, package_id)
    assert pkg is not None
    return pkg
