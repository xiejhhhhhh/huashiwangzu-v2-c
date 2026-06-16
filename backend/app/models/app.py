from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text, JSON, DateTime, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class App(Base, TimestampMixin):
    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="Unique identifier, e.g. knowledge, agent")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Display name")
    app_type: Mapped[str] = mapped_column(String(32), default="builtin", comment="builtin | custom")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="App description")
    route_prefix: Mapped[str] = mapped_column(String(255), default="", comment="API route prefix")
    component_key: Mapped[str] = mapped_column(String(128), default="", comment="Frontend component key")
    icon: Mapped[str] = mapped_column(String(100), nullable=False, default="Collection", comment="Element Plus icon name")
    category: Mapped[str] = mapped_column(String(64), default="", comment="Grouping category")
    permissions: Mapped[dict] = mapped_column(JSON, default=list, comment="Allowed roles: list of role names")
    required_permission: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None, comment="Fine-grained permission key")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="Display order, ascending")

    # Window geometry
    default_width: Mapped[int] = mapped_column(Integer, default=900)
    default_height: Mapped[int] = mapped_column(Integer, default=600)
    min_width: Mapped[int] = mapped_column(Integer, default=400, comment="Minimum window width")
    min_height: Mapped[int] = mapped_column(Integer, default=300, comment="Minimum window height")

    # Window behavior
    singleton: Mapped[bool] = mapped_column(Boolean, default=True, comment="Global singleton instance")
    allow_multiple: Mapped[bool] = mapped_column(Boolean, default=False, comment="Allow multiple instances")
    resizable: Mapped[bool] = mapped_column(Boolean, default=True)
    window_type: Mapped[str] = mapped_column(String(32), default="normal", comment="normal | tool | panel | fullscreen | background")

    # Visibility toggles
    show_on_desktop: Mapped[bool] = mapped_column(Boolean, default=False, comment="Show icon on desktop")
    show_in_tray: Mapped[bool] = mapped_column(Boolean, default=False, comment="Show in system tray")
    show_in_launcher: Mapped[bool] = mapped_column(Boolean, default=True, comment="Show in launcher / start menu")
    show_in_sidebar: Mapped[bool] = mapped_column(Boolean, default=False, comment="Show in right sidebar")

    # File associations
    supported_formats: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Openable file extensions")
    editable_formats: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Editable file extension subset")

    # Enabled state
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="Enabled / disabled")
    needs_frontend_build: Mapped[bool] = mapped_column(Boolean, default=False, comment="Requires npm build after update")
    manifest_hash: Mapped[str] = mapped_column(String(64), default="", comment="Manifest file hash")
    last_scan_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="Last scan timestamp")

    # Capabilities & actions
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="App capability declarations")
    public_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Public action declarations")

    # Version info
    module_version: Mapped[str] = mapped_column(String(32), default="1.0.0", comment="Module version")
    contract_version: Mapped[str] = mapped_column(String(32), default="2.0", comment="Manifest contract version")
    installed_version: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="Installed version")
    framework_min_version: Mapped[str] = mapped_column(String(32), default="1.0.0", comment="Minimum framework version")
    framework_max_version: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="Maximum framework version")

    # V2 declaration fields
    permission_declaration: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Permission declarations")
    db_migration_declaration: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="DB migration declarations")
    event_handler_declaration: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Event handler declarations")
    dependency_declaration: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Dependency declarations")
    openable_types_declaration: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="Openable file type declarations")

    def __repr__(self) -> str:
        return f"<App id={self.id} key={self.key} name={self.name}>"
