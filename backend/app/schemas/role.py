from pydantic import BaseModel


class RoleMatrixItem(BaseModel):
    role_key: str
    display_name: str
    permissions: dict[str, bool]


class RoleMatrixResponse(BaseModel):
    matrix: list[RoleMatrixItem]


class RoleMatrixUpdate(BaseModel):
    matrix: list[RoleMatrixItem]


class RoleInfo(BaseModel):
    key: str
    name: str