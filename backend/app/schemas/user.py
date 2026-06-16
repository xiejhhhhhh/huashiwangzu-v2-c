from pydantic import BaseModel, Field
from datetime import datetime


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None = None
    role: str
    enabled: bool
    last_login: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=1)
    email: str | None = None
    role: str = "viewer"


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1)
    email: str | None = None
    password: str | None = Field(None, min_length=6)
    role: str | None = None
    enabled: bool | None = None


class UserSearchRequest(BaseModel):
    keyword: str = ""
