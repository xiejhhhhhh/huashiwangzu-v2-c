from pydantic import BaseModel
from datetime import datetime


class RecycleItemResponse(BaseModel):
    id: int
    origin_id: int
    item_type: str
    name: str
    deleted_at: datetime

    model_config = {"from_attributes": True}


class RecycleListResponse(BaseModel):
    items: list[RecycleItemResponse]


class RestoreRequest(BaseModel):
    item_type: str
    id: int
