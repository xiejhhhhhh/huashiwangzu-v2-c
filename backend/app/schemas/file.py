from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FolderResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileResponse(BaseModel):
    id: int
    name: str
    extension: str
    size: int
    folder_id: Optional[int] = None
    mime_type: str
    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        return f"{self.name}.{self.extension}" if self.extension else self.name

    model_config = {"from_attributes": True}


class FileListItem(BaseModel):
    id: int
    name: str
    extension: Optional[str] = None
    size: int
    parent_id: Optional[int] = None
    created_at: Optional[datetime] = None
    is_folder: bool
    mime_type: Optional[str] = None
    storage_path: Optional[str] = None


class FileListResponse(BaseModel):
    items: list[FileListItem]
    total: int
    page: int
    page_size: int


class UploadResponse(BaseModel):
    id: int
    name: str
    extension: str
    size: Optional[int] = None
    mime_type: Optional[str] = None
    exists: bool = False


class PreviewResponse(BaseModel):
    content: Optional[str] = None
    format: Optional[str] = None
    file_info: dict
    mime_type: Optional[str] = None
    download_url: Optional[str] = None


class CreateFolderRequest(BaseModel):
    name: str
    parent_id: Optional[int] = None


class RenameRequest(BaseModel):
    type: str  # "file" or "folder"
    id: int
    new_name: str


class MoveRequest(BaseModel):
    type: str
    id: int
    target_folder_id: Optional[int] = None


class DeleteRequest(BaseModel):
    type: str  # "file" or "folder"
    id: int


class SearchRequest(BaseModel):
    keyword: str = ""
    extension: Optional[str] = None
    page: int = 1
    page_size: int = 50
