from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.desktop_state import DesktopState


async def get_state(db: AsyncSession, user_id: int):
    result = await db.execute(select(DesktopState).where(DesktopState.user_id == user_id))
    return result.scalar_one_or_none()


async def save_state(db: AsyncSession, user_id: int, state_json: dict):
    state = await get_state(db, user_id)
    if state:
        state.state_json = state_json
        state.version += 1
    else:
        state = DesktopState(user_id=user_id, state_json=state_json, version=1)
        db.add(state)
    await db.commit()
    await db.refresh(state)
    return state
