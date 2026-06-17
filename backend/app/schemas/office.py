from pydantic import BaseModel
from datetime import datetime


class PackageStatusResponse(BaseModel):
    file_id: int
    file_name: str
    has_package: bool
    package_id: int | None = None
    current_version_id: int | None = None
    package_status: str = "not_generated"
    summary: str | None = None
    last_updated: str | None = None

    model_config = {"from_attributes": True}


class CreatePackageResponse(BaseModel):
    package_id: int
    version_id: int
    package_status: str


class PackageDetailResponse(BaseModel):
    package: dict | None = None
    version: dict | None = None
    json_content: dict = {}
    unified_view: dict | None = None


class VersionItem(BaseModel):
    id: int
    package_id: int
    version_number: int
    summary: str | None
    creator_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PatchItem(BaseModel):
    id: int
    package_id: int
    source_version_id: int
    target_version_id: int
    operation_type: str
    json_path: str
    before_summary: str | None
    after_content: str
    risk_level: str
    reason: str | None
    patch_status: str
    creator_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RollbackResponse(BaseModel):
    new_version_id: int
    new_version_number: int
    message: str


class ApplyPatchResponse(BaseModel):
    new_version_id: int
    new_version_number: int
    message: str


class PatchPreviewResponse(BaseModel):
    preview_passed: bool
    risk_level: str = "medium"
    sheet: str | None = None
    cell: str | None = None
    target_id: str | None = None


class PatchRequest(BaseModel):
    package_id: int
    patch: dict


class RollbackRequest(BaseModel):
    package_id: int
    target_version_id: int


class TextReadResponse(BaseModel):
    content: str
    mtime: str | None = None

    model_config = {"from_attributes": True}


class TextSaveRequest(BaseModel):
    content: str
    mtime: str | None = None


class CsvReadResponse(BaseModel):
    content: str
    delimiter: str = ","
    mtime: str | None = None

    model_config = {"from_attributes": True}


class CsvSaveRequest(BaseModel):
    content: str
    delimiter: str = ","
    mtime: str | None = None


class ExportResponse(BaseModel):
    message: str
