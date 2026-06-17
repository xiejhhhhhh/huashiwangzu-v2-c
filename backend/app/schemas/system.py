from pydantic import BaseModel
from datetime import datetime

class SystemLogResponse(BaseModel):
    id: int; level: str; module: str; action: str; message: str
    user_id: int | None; ip_address: str; duration_ms: int; created_at: datetime
    model_config = {"from_attributes": True}

class SystemLogDetailResponse(SystemLogResponse):
    request_data: dict | None

class LogFilterParams(BaseModel):
    level: str | None = None
    module: str | None = None
    keyword: str | None = None
    page: int = 1
    page_size: int = 20

class FrontendErrorRequest(BaseModel):
    url: str = ""; status_code: int = 0; error_message: str = ""; page_path: str = ""

class NotificationResponse(BaseModel):
    id: int; title: str; content: str; notification_type: str; status: str
    publisher_id: int; published_at: datetime | None; is_read: bool = False; created_at: datetime
    model_config = {"from_attributes": True}

class NotificationAdminResponse(BaseModel):
    id: int; title: str; content: str; notification_type: str; status: str
    publisher_id: int; published_at: datetime | None; created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}

class NotificationCreate(BaseModel):
    title: str; content: str = ""; notification_type: str = "system"

class FeedbackResponse(BaseModel):
    id: int; user_id: int; feedback_type: str; content: str; status: str
    page_url: str; user_agent: str; admin_note: str | None; handler_id: int | None
    handled_at: datetime | None; created_at: datetime
    model_config = {"from_attributes": True}

class FeedbackCreate(BaseModel):
    feedback_type: str = "bug"; content: str; page_url: str = ""; user_agent: str = ""

class FeedbackStatusUpdate(BaseModel):
    status: str; admin_note: str | None = None

class TaskResponse(BaseModel):
    id: int; title: str; description: str; status: str; priority: str
    assignee_id: int | None; created_at: datetime
    model_config = {"from_attributes": True}

class DashboardOverview(BaseModel):
    total_users: int; online_users: int; total_files: int; total_logs: int
    pending_tasks: int; system_version: str; project_name: str

class RecentLogItem(BaseModel):
    id: int; level: str; module: str; message: str; created_at: datetime

class RecentTaskItem(BaseModel):
    id: int; task_type: str; status: str; created_at: datetime

class HealthCheckItem(BaseModel):
    status: bool; message: str

class SystemStatusResponse(BaseModel):
    backend: HealthCheckItem; database: HealthCheckItem; worker: HealthCheckItem
    model_service: HealthCheckItem; entry: HealthCheckItem
    cpu_percent: float; memory_percent: float

class SettingResponse(BaseModel):
    id: int; key: str; value: str; description: str
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}

class SettingCreate(BaseModel):
    key: str; value: str = ""; description: str = ""

class SettingUpdate(BaseModel):
    value: str; description: str | None = None

class BackupItem(BaseModel):
    backup_name: str; backup_time: str; database_name: str; backup_size: str; backup_status: str

class BackupDetailResponse(BaseModel):
    backup_name: str; backup_time: str; database_name: str
    backup_size: str; backup_status: str; file_count: int; file_list: list[dict]

class SystemTaskQueueResponse(BaseModel):
    id: int; task_type: str; status: str; priority: int; module: str
    retry_count: int; max_retries: int; error_message: str | None
    created_at: datetime | None; started_at: datetime | None; completed_at: datetime | None
    model_config = {"from_attributes": True}

class WorkerStatusResponse(BaseModel):
    pending: int; running: int; completed: int; failed: int; oldest_waiting_seconds: int | None
