"""Excel Engine - Database models.

Maps to old project tables: 桌面_Excel_工作簿, 桌面_Excel_子表, 桌面_Excel_单元格,
桌面_Excel_列宽, 桌面_Excel_行高, 桌面_Excel_历史, 桌面_Excel_恢复栈, 桌面_Excel_版本
"""
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, BigInteger, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ExcelWorkbook(Base):
    """工作簿表 - mirrors old 桌面_Excel_工作簿"""
    __tablename__ = "excel_workbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment="状态键，如 knowledge_123")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled", comment="工作簿名称")
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="创建者用户ID")
    upload_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上传时间")
    timeout_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="超时时间")
    last_active_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最后活跃时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_excel_wb_state_key", "state_key"),
    )


class ExcelSheet(Base):
    """子表表 - mirrors old 桌面_Excel_子表"""
    __tablename__ = "excel_sheets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workbook_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属工作簿id")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Sheet1", comment="子表名称")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=40, comment="总行数")
    total_cols: Mapped[int] = mapped_column(Integer, nullable=False, default=10, comment="总列数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_excel_sheet_wb", "workbook_id"),
    )


class ExcelCell(Base):
    """单元格表 - mirrors old 桌面_Excel_单元格"""
    __tablename__ = "excel_cells"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属子表id")
    cell_addr: Mapped[str] = mapped_column(String(16), nullable=False, comment="单元格地址 A1")
    cell_value: Mapped[str | None] = mapped_column(Text, nullable=True, comment="单元格值")
    style_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="样式JSON")
    merge_info: Mapped[str | None] = mapped_column(Text, nullable=True, comment="合并信息JSON")

    __table_args__ = (
        Index("idx_excel_cell_sheet_addr", "sheet_id", "cell_addr", unique=True),
    )


class ExcelColWidth(Base):
    """列宽表 - mirrors old 桌面_Excel_列宽"""
    __tablename__ = "excel_col_widths"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    col_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="列号 0-based")
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=80)

    __table_args__ = (
        Index("idx_excel_colw_sheet", "sheet_id", "col_index", unique=True),
    )


class ExcelRowHeight(Base):
    """行高表 - mirrors old 桌面_Excel_行高"""
    __tablename__ = "excel_row_heights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="行号 1-based")
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=24)

    __table_args__ = (
        Index("idx_excel_rowh_sheet", "sheet_id", "row_index", unique=True),
    )


class ExcelHistory(Base):
    """操作历史表 - mirrors old 桌面_Excel_历史"""
    __tablename__ = "excel_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属子表id")
    action: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作类型")
    cell_addr: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="地址")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="描述")
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="快照数据JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_excel_hist_sheet", "sheet_id"),
    )


class ExcelRedoStack(Base):
    """恢复栈表 - mirrors old 桌面_Excel_恢复栈"""
    __tablename__ = "excel_redo_stack"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cell_addr: Mapped[str | None] = mapped_column(String(16), nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_excel_redo_sheet", "sheet_id"),
    )


class ExcelVersion(Base):
    """版本表 - mirrors old 桌面_Excel_版本"""
    __tablename__ = "excel_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="关联文件id")
    version_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="版本名")
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_steps: Mapped[int] = mapped_column(Integer, default=0)
    creator_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_excel_ver_file", "file_id"),
    )
