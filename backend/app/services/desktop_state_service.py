from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.desktop_state import DesktopState


async def get_state(db: AsyncSession, user_id: int):
    result = await db.execute(select(DesktopState).where(DesktopState.user_id == user_id))
    return result.scalar_one_or_none()


async def save_state(
    db: AsyncSession,
    user_id: int,
    state_json: dict,
    *,
    expected_version: int | None = None,
):
    """保存桌面状态。WP6：带 expected_version 时做 CAS，冲突返回 409。

    - expected_version is None：兼容旧客户端，直接覆盖并 version+1
    - expected_version 有值：必须等于当前 version，否则 ConflictError(DESKTOP_STATE_CONFLICT)
    """
    state = await get_state(db, user_id)
    if state:
        if expected_version is not None and int(state.version) != int(expected_version):
            raise ConflictError(
                f"DESKTOP_STATE_CONFLICT: expected {expected_version}, current {state.version}"
            )
        state.state_json = state_json
        state.version += 1
    else:
        if expected_version is not None and int(expected_version) not in (0, 1):
            # 无状态时只接受 0/1 作为“从空创建”
            raise ConflictError(
                f"DESKTOP_STATE_CONFLICT: expected {expected_version}, current 0"
            )
        state = DesktopState(user_id=user_id, state_json=state_json, version=1)
        db.add(state)
    await db.commit()
    await db.refresh(state)
    return state
