from pydantic import BaseModel
from typing import Any
from datetime import datetime


class AppResponse(BaseModel):
    id: int
    app_id: str
    name: str
    app_type: str = "builtin"
    description: str = ""
    icon: str
    category: str = ""
    entry_component_key: str = ""
    route_prefix: str = ""
    permissions: list[str] = []
    required_permission: str | None = None
    sort_order: int = 0
    default_width: int = 900
    default_height: int = 600
    min_width: int = 400
    min_height: int = 300
    singleton: bool = True
    allow_multiple: bool = False
    resizable: bool = True
    window_type: str = "normal"
    show_on_desktop: bool = False
    show_in_tray: bool = False
    show_in_launcher: bool = True
    show_in_sidebar: bool = False
    supported_formats: Any = None
    editable_formats: Any = None
    enabled: bool = True
    needs_frontend_build: bool = False
    manifest_hash: str = ""
    last_scan_time: str | None = None
    capabilities: Any = None
    public_actions: Any = None
    module_version: str = "1.0.0"
    contract_version: str = "2.0"
    installed_version: str | None = None
    framework_min_version: str = "1.0.0"
    framework_max_version: str | None = None
    permission_declaration: Any = None
    db_migration_declaration: Any = None
    event_handler_declaration: Any = None
    dependency_declaration: Any = None
    openable_types_declaration: Any = None


class AppUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    category: str | None = None
    permissions: list[str] | None = None
    sort_order: int | None = None
    enabled: bool | None = None
    default_width: int | None = None
    default_height: int | None = None
    singleton: bool | None = None
    allow_multiple: bool | None = None
    window_type: str | None = None
    show_on_desktop: bool | None = None
    show_in_tray: bool | None = None
    show_in_launcher: bool | None = None
    show_in_sidebar: bool | None = None


class AppCreateRequest(BaseModel):
    key: str
    name: str
    icon: str = "Collection"
    description: str | None = None
    component_key: str = ""
    route_prefix: str = ""
    category: str = ""
    permissions: list[str] = []
    sort_order: int = 0
    default_width: int = 900
    default_height: int = 600
    singleton: bool = True
    allow_multiple: bool = False
    window_type: str = "normal"
    show_on_desktop: bool = False
    show_in_tray: bool = False
    show_in_launcher: bool = True
    show_in_sidebar: bool = False
    enabled: bool = True
