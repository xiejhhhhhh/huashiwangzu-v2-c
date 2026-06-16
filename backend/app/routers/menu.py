from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.app_service import app_to_dict, list_apps

router = APIRouter(prefix="/api/menu", tags=["menu"])


@router.get("")
async def get_menu(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("viewer")),
):
    apps = await list_apps(db, user)
    items = [
        {
            "key": app.key, "name": app.name, "icon": app.icon,
            "category": app.category, "routePrefix": app.route_prefix,
            "componentKey": app.component_key, "sortOrder": app.sort_order,
            "app": app_to_dict(app),
        }
        for app in apps if app.show_in_launcher or app.show_on_desktop
    ]
    return ApiResponse(data={"items": items})
