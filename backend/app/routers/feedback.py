from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.system import FeedbackCreate, FeedbackResponse, FeedbackStatusUpdate
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.services import feedback_service as svc

router = APIRouter(tags=["feedback"])


@router.post("/api/feedback")
async def submit_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("viewer")),
):
    fb = await svc.submit_feedback(db, user.id, body.feedback_type, body.content, body.page_url, body.user_agent)
    return ApiResponse(data=FeedbackResponse.model_validate(fb))


@router.get("/api/feedback/admin/list")
async def list_feedbacks(
    page: int = Query(1), page_size: int = Query(15),
    status: str | None = Query(None), feedback_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin")),
):
    items, total = await svc.list_feedbacks(db, page, page_size, status, feedback_type)
    return ApiResponse(data={
        "list": [FeedbackResponse.model_validate(i) for i in items],
        "total": total, "page": page, "page_size": page_size,
    })


@router.get("/api/feedback/admin/{fid}")
async def get_feedback_detail(
    fid: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin")),
):
    fb = await svc.get_feedback_detail(db, fid)
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return ApiResponse(data=FeedbackResponse.model_validate(fb))


@router.put("/api/feedback/admin/{fid}/status")
async def update_feedback_status(
    fid: int, body: FeedbackStatusUpdate,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_permission("admin")),
):
    fb = await svc.update_feedback_status(db, fid, body.status, body.admin_note, user.id)
    if not fb:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return ApiResponse(data=FeedbackResponse.model_validate(fb))
