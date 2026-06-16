from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.knowledge import Evidence
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.knowledge import EvidenceBindConclusionRequest
from app.services.knowledge.governance_presenter import evidence_dict

router = APIRouter(prefix="/api/knowledge/evidences", tags=["knowledge-evidence-write"])


@router.post("/{evidence_id}/bind-conclusions")
async def bind_evidence_conclusions(
    evidence_id: int,
    body: EvidenceBindConclusionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("editor")),
):
    evidence = await db.get(Evidence, evidence_id)
    if not evidence:
        raise NotFound("Evidence not found")
    evidence.bound_conclusions = {
        "conclusions": body.conclusions,
        "note": body.note,
        "binderUserId": user.id,
    }
    await db.commit()
    await db.refresh(evidence)
    return ApiResponse(data=evidence_dict(evidence))
