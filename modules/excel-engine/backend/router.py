"""FastAPI router for excel-engine module.

1:1 translation of old 表格.php API entry + 表格_调用.php routing.
All operations go through this unified router.
"""
import json
import os
import tempfile
from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.core.exceptions import NotFound
from app.services.file_service import check_file_access
from app.services.module_registry import register_capability

from .state.manager import (
    init_state, cell_set_text, cell_get_style_ref,
    parse_addresses, empty_state,
    TEMP_DIR,
)
from .state.db_ops import (
    find_or_create_workbook, find_or_create_sheet,
    read_state_full, read_history, record_snapshot,
    undo_operation, redo_operation, history_preview,
    sync_cells, sync_col_widths, sync_row_heights,
    find_workbook, find_sheet,
)
from .table.edit import EditOperations
from .table.style_ops import StyleOperations
from .table.clipboard import ClipboardOperations
from .table.row_col import RowColOperations
from .engine.xlsx_parser import parse_xlsx
from .engine.csv_parser import parse_csv
from .engine.xlsx_generator import generate_xlsx
from .tool.config import DEFAULT_TOTAL_ROWS, DEFAULT_TOTAL_COLS

# Constants matching old project
WRITE_OPERATIONS = [
    'edit.input', 'edit.batch_fill', 'edit.clear', 'edit.hyperlink', 'edit.format',
    'style.bold', 'style.italic', 'style.underline', 'style.strikethrough',
    'style.align_left', 'style.align_center', 'style.align_right',
    'style.font', 'style.font_size', 'style.fill_color', 'style.font_color',
    'style.wrap_text', 'style.border',
    'clipboard.paste', 'export.save_version',
    'table.merge', 'table.sort',
    'table.delete_shift_right', 'table.delete_shift_up',
    'table.delete_row', 'table.delete_col',
    'table.insert_shift_right', 'table.insert_shift_down',
    'table.insert_row_above', 'table.insert_row_below',
    'table.insert_col_left', 'table.insert_col_right',
]

# Setup temp dir
_init_temp = os.path.join(os.path.dirname(__file__), '..', 'temp_files')
os.makedirs(_init_temp, exist_ok=True)
init_state(_init_temp)

router = APIRouter(prefix="/api/excel-engine", tags=["excel-engine"])


def _resolve_user_id(caller: str) -> int:
    from app.core.exceptions import PermissionDenied

    try:
        prefix, raw_id = caller.split(":", 1)
        if prefix == "user":
            return int(raw_id)
    except (TypeError, ValueError):
        pass
    raise PermissionDenied("Invalid caller")


# ── Schema ──

class ExcelRequest(BaseModel):
    module: str = ''
    method: str = ''
    params: dict = {}
    state_key: str = ''
    sheet: str = 'Sheet1'


class OpenRequest(BaseModel):
    file_id: int
    target_sheet: str = ''


class SaveRequest(BaseModel):
    state_key: str
    sheet: str = 'Sheet1'


class CellEditRequest(BaseModel):
    state_key: str
    sheet: str = 'Sheet1'
    address: str = ''
    address_list: list[str] = []
    value: str = ''
    method: str = 'input'
    params: dict = {}


class StyleRequest(BaseModel):
    state_key: str
    sheet: str = 'Sheet1'
    address_list: list[str] = []
    method: str = ''
    params: dict = {}


class ClipboardRequest(BaseModel):
    state_key: str
    sheet: str = 'Sheet1'
    address: str = ''
    address_list: list[str] = []
    method: str = ''
    params: dict = {}


class TableRequest(BaseModel):
    state_key: str
    sheet: str = 'Sheet1'
    address: str = ''
    address_list: list[str] = []
    method: str = ''
    params: dict = {}


# ── Helper: description generation (1:1 from 表格_生成描述) ──

DESCRIPTION_MAP = {
    'edit.input': '输入', 'edit.batch_fill': '批量填充', 'edit.clear': '清除',
    'edit.hyperlink': '超链接', 'edit.format': '设置格式',
    'style.bold': '加粗', 'style.italic': '倾斜', 'style.underline': '下划线',
    'style.strikethrough': '删除线', 'style.align_left': '左对齐',
    'style.align_center': '居中', 'style.align_right': '右对齐',
    'style.font': '设置字体', 'style.font_size': '设置字号',
    'style.fill_color': '填充色', 'style.font_color': '字体色',
    'style.wrap_text': '换行', 'style.border': '边框',
    'clipboard.paste': '粘贴', 'export.save_version': '保存版本',
    'table.merge': '合并', 'table.sort': '排序',
    'table.delete_row': '删除行', 'table.delete_col': '删除列',
    'table.insert_row_above': '插入行上', 'table.insert_row_below': '插入行下',
    'table.insert_col_left': '插入列左', 'table.insert_col_right': '插入列右',
}


def _generate_description(op_key: str, addr: str = '', addrs: list[str] | None = None, params: dict | None = None) -> str:
    params = params or {}
    addrs = addrs or []
    op_name = DESCRIPTION_MAP.get(op_key, op_key)
    target = ''

    if op_key == 'edit.input':
        val = params.get('value', '')
        if len(val) > 15:
            val = val[:15] + '…'
        target = f'输入：{val}' if val else '输入：（空）'
    elif op_key == 'edit.clear':
        ct = params.get('type', 'all')
        type_names = {'all': '内容与格式', 'format': '格式', 'content': '内容'}
        target = f'清除{type_names.get(ct, ct)}'
    elif op_key == 'edit.batch_fill':
        target = f'填充 {len(params.get("fill_list", []))} 格'
    elif op_key == 'style.fill_color':
        target = f'填充色 → {params.get("color", "无")}'
    elif op_key == 'style.font_color':
        target = f'字体色 → {params.get("color", "无")}'
    elif op_key == 'style.font':
        target = f'字体：{params.get("value", "宋体")}'
    elif op_key == 'style.font_size':
        target = f'字号：{params.get("value", "11")}'
    elif op_key in ('table.delete_row', 'table.delete_col',
                    'table.insert_row_above', 'table.insert_row_below',
                    'table.insert_col_left', 'table.insert_col_right'):
        target = f'{op_name} @ {addr}'
    else:
        target = op_name

    display_addr = addr or (addrs[0] if addrs else '')
    if display_addr and display_addr not in target:
        return f'{display_addr} {target}'
    return target


# ── Core dispatch (1:1 from 表格_调用) ──

async def _dispatch(
    module: str, method: str, params: dict,
    state_key: str, sheet: str, db: AsyncSession,
    state: dict | None = None,
    owner_id: int = 0
) -> dict:
    """Unified dispatch matching old 表格_调用::调用"""
    load_state = state is None

    if module == 'load':
        return await _handle_load(method, params, db)

    if module == 'state' and method in ('archive_timeout', 'archive', 'workbook_list'):
        return await _handle_state_direct(method, params, db)

    if load_state:
        state = await read_state_full(db, state_key, sheet, owner_id=owner_id)
        if not state.get('cells'):
            state = empty_state(sheet)

    addrs = parse_addresses(params)
    op_key = f'{module}.{method}'

    if op_key in WRITE_OPERATIONS:
        await record_snapshot(db, state, state_key, op_key, addrs[0] if addrs else '',
                              _generate_description(op_key, addrs[0] if addrs else '', addrs, params),
                              owner_id=owner_id)
        # Clear redo stack
        sheet_id = state.get('_sheet_id')
        if sheet_id and hasattr(db, 'execute'):
            from sqlalchemy import text
            from .state.db_ops import ExcelRedoStack
            await db.execute(
                text(f"DELETE FROM {ExcelRedoStack.__tablename__} WHERE sheet_id = :sid"),
                {'sid': sheet_id}
            )
            await db.commit()

    result = None
    if module == 'edit':
        result = await EditOperations.execute(method, state, state_key, addrs, params)
    elif module == 'style':
        result = await StyleOperations.execute(method, state, state_key, addrs, params)
    elif module == 'clipboard':
        result = await ClipboardOperations.execute(method, state, state_key, addrs, params)
    elif module == 'table':
        result = await RowColOperations.execute(method, state, state_key, addrs, params)
    elif module == 'state':
        result = await _handle_state(method, state, state_key, params, sheet, db)
    elif module == 'export':
        result = await _handle_export(method, state, state_key, sheet, params, db)
    elif module == 'import':
        result = await _handle_import_method(method, state, state_key, params, db)

    if result is None:
        result = {'code': 1, 'msg': f'Unknown module: {module}'}

    # Persist state after write operations (skip for download exports)
    if op_key in WRITE_OPERATIONS and not (module == 'export' and method == 'download'):
        workbook_id = state.get('_workbook_id') or (await find_or_create_workbook(db, state_key, owner_id=owner_id))['id']
        sheet_id = state.get('_sheet_id')
        if not sheet_id:
            sheet_rec = await find_or_create_sheet(db, workbook_id, state.get('_current_sheet', sheet))
            sheet_id = sheet_rec['id']
        state['total_rows'] = state.get('total_rows', DEFAULT_TOTAL_ROWS)
        state['total_cols'] = state.get('total_cols', DEFAULT_TOTAL_COLS)
        await sync_cells(db, sheet_id, state.get('cells', {}), state.get('styles', {}), state.get('merges', {}))
        await sync_col_widths(db, sheet_id, state.get('col_widths', {}))
        await sync_row_heights(db, sheet_id, state.get('row_heights', {}))

    if result and result.get('code') == 0:
        result.setdefault('cells', state.get('cells', {}))
        result.setdefault('styles', state.get('styles', {}))
        result.setdefault('merges', state.get('merges', {}))
        result.setdefault('total_rows', state.get('total_rows', DEFAULT_TOTAL_ROWS))
        result.setdefault('total_cols', state.get('total_cols', DEFAULT_TOTAL_COLS))
        hist_list = await read_history(db, state_key)
        result['history_count'] = len(hist_list)

    return result


async def _handle_load(method: str, params: dict, db: AsyncSession) -> dict:
    """Handle load operations"""
    if method == 'load_window':
        file_id = params.get('file_id', 0)
        state_key = f'knowledge_{file_id}'
        state = await read_state_full(db, state_key)
        return {
            'code': 0,
            'cells': state.get('cells', {}),
            'styles': state.get('styles', {}),
            'merges': state.get('merges', {}),
            'col_widths': state.get('col_widths', {}),
            'row_heights': state.get('row_heights', {}),
            'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
            'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
            'all_sheets': state.get('all_sheets', ['Sheet1']),
            'sheet_set': state.get('sheet_set', {}),
            'state_key': state_key,
            '_current_sheet': state.get('_current_sheet', 'Sheet1'),
            '_workbook_id': state.get('_workbook_id'),
            '_sheet_id': state.get('_sheet_id'),
        }
    return {'code': 1, 'msg': f'Unknown load method: {method}'}


async def _handle_state(method: str, state: dict, state_key: str, params: dict, sheet: str, db: AsyncSession) -> dict:
    if method == 'read':
        return {
            'code': 0, 'cells': state.get('cells', {}), 'styles': state.get('styles', {}),
            'merges': state.get('merges', {}), 'col_widths': state.get('col_widths', {}),
            'row_heights': state.get('row_heights', {}),
            'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
            'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
        }
    elif method == 'undo':
        success = await undo_operation(db, state, state_key)
        return {'code': 0 if success else 1, 'msg': '' if success else '无可撤销操作'}
    elif method == 'redo':
        success = await redo_operation(db, state, state_key)
        return {'code': 0 if success else 1, 'msg': '' if success else '无可恢复操作'}
    elif method == 'history_list':
        hist = await read_history(db, state_key)
        return {'code': 0, 'history': hist}
    elif method == 'history_preview':
        hist_id = int(params.get('history_id', 0))
        sheet_id = state.get('_sheet_id', 0)
        snapshot = await history_preview(db, hist_id, sheet_id)
        if snapshot:
            return {
                'code': 0, 'cells': snapshot.get('cells', {}),
                'styles': snapshot.get('styles', {}),
                'merges': snapshot.get('merges', {}),
                'total_rows': snapshot.get('total_rows', DEFAULT_TOTAL_ROWS),
                'total_cols': snapshot.get('total_cols', DEFAULT_TOTAL_COLS),
                'col_widths': snapshot.get('col_widths', {}),
                'row_heights': snapshot.get('row_heights', {}),
            }
        return {'code': 1, 'msg': '历史记录不存在'}
    return {'code': 1, 'msg': f'Unknown state method: {method}'}


async def _handle_state_direct(method: str, params: dict, db: AsyncSession) -> dict:
    if method == 'workbook_list':
        from sqlalchemy import text
        from ..models import ExcelWorkbook
        result = await db.execute(
            text(f"SELECT id, name, upload_time FROM {ExcelWorkbook.__tablename__} ORDER BY last_active_time DESC")
        )
        items = [{'id': r[0], 'name': r[1], 'upload_time': str(r[2])} for r in result.fetchall()]
        return {'code': 0, 'workbooks': items}
    return {'code': 1, 'msg': f'Unknown direct state method: {method}'}


async def _handle_export(method: str, state: dict, state_key: str, sheet: str, params: dict, db: AsyncSession) -> dict:
    if method == 'download':
        from .state.db_ops import build_snapshot
        all_sheet_data = {}
        sheet_set_raw = state.get('sheet_set', {})
        first = next(iter(sheet_set_raw.values()), None) if sheet_set_raw else None
        is_data_map = isinstance(first, dict) and 'cells' in first

        if is_data_map:
            for s_name, s_data in sheet_set_raw.items():
                all_sheet_data[s_name] = {
                    'cells': s_data.get('cells', {}),
                    'styles': s_data.get('styles', {}),
                    'merges': s_data.get('merges', {}),
                    'col_widths': s_data.get('col_widths', {}),
                    'row_heights': s_data.get('row_heights', {}),
                    'total_rows': s_data.get('total_rows', DEFAULT_TOTAL_ROWS),
                    'total_cols': s_data.get('total_cols', DEFAULT_TOTAL_COLS),
                }

        current_name = sheet or (state.get('all_sheets', ['Sheet1'])[0])
        all_sheet_data.setdefault(current_name, {
            'cells': state.get('cells', {}),
            'styles': state.get('styles', {}),
            'merges': state.get('merges', {}),
            'col_widths': state.get('col_widths', {}),
            'row_heights': state.get('row_heights', {}),
            'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
            'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
        })

        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        success = generate_xlsx(tmp_path, all_sheet_data)
        if not success:
            return {'code': 1, 'msg': '导出失败'}

        return {'code': 0, 'file': tmp_path, 'filename': f'{state_key}.xlsx'}
    elif method == 'data':
        return {
            'code': 0,
            'data': {
                'cells': state.get('cells', {}),
                'styles': state.get('styles', {}),
                'merges': state.get('merges', {}),
                'sheet': sheet,
            }
        }
    elif method == 'csv':
        from ..engine.xlsx_generator import generate_csv
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        csv_content = generate_csv(tmp_path, state, sheet)
        return {'code': 0, 'csv': csv_content}
    return {'code': 1, 'msg': f'Unknown export method: {method}'}


async def _handle_import_method(method: str, state: dict, state_key: str, params: dict, db: AsyncSession) -> dict:
    return {'code': 1, 'msg': f'Unknown import method: {method}'}


# ── API Endpoints ──

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "excel-engine", "status": "ok"})


@router.post("/parse")
async def parse_xlsx_file(payload: OpenRequest, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_permission("viewer"))):
    """Parse XLSX/CSV file from file storage"""
    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError
    from pathlib import Path

    allowed = {"xlsx", "xls", "csv"}
    file = await check_file_access(db, payload.file_id, user.id)
    ext = (file.extension or "").lower()
    if ext not in allowed:
        raise ValidationError(f"Unsupported format '{ext}'")

    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    full_path = (upload_root / file.storage_path).resolve()
    if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root) or not full_path.exists():
        raise NotFound("File on disk not found")

    if ext in ("xlsx", "xls"):
        result = parse_xlsx(str(full_path), file.name, payload.target_sheet)
    elif ext == "csv":
        result = parse_csv(str(full_path), file.name)
    else:
        raise ValidationError(f"Unsupported format '{ext}'")

    return ApiResponse(data=result)


@router.post("/open")
async def open_xlsx(payload: OpenRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("viewer"))):
    """Open XLSX file - loads into DB state and returns initialized state"""
    from app.config import get_settings
    from app.core.exceptions import NotFound, ValidationError, AppException
    from pathlib import Path

    file = await check_file_access(db, payload.file_id, user.id)
    ext = (file.extension or "").lower()
    state_key = f'knowledge_{payload.file_id}'

    # Check if already loaded
    existing = await find_workbook(db, state_key)
    if existing:
        state = await read_state_full(db, state_key, payload.target_sheet or 'Sheet1', owner_id=user.id)
        return ApiResponse(data={
            'state_key': state_key,
            'cells': state.get('cells', {}),
            'styles': state.get('styles', {}),
            'merges': state.get('merges', {}),
            'col_widths': state.get('col_widths', {}),
            'row_heights': state.get('row_heights', {}),
            'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
            'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
            'all_sheets': state.get('all_sheets', ['Sheet1']),
            'sheet_set': state.get('sheet_set', {}),
        })

    # Parse and save to DB
    upload_root = Path(get_settings().UPLOAD_DIR).resolve()
    full_path = (upload_root / file.storage_path).resolve()

    if ext in ("xlsx", "xls"):
        result = parse_xlsx(str(full_path), file.name, payload.target_sheet)
    elif ext == "csv":
        result = parse_csv(str(full_path), file.name)
    else:
        raise ValidationError(f"Unsupported format")

    if result.get('code') != 0:
        raise AppException(result.get('msg', 'Parse failed'))

    wb = await find_or_create_workbook(db, state_key, owner_id=user.id)
    sheet_name = payload.target_sheet or (result.get('all_sheets', ['Sheet1'])[0])

    if 'sheet_set' in result:
        for s_name, s_data in result['sheet_set'].items():
            sheet_rec = await find_or_create_sheet(
                db, wb['id'], s_name, s_data.get('total_rows', DEFAULT_TOTAL_ROWS), s_data.get('total_cols', DEFAULT_TOTAL_COLS)
            )
            await sync_cells(db, sheet_rec['id'], s_data.get('cells', {}), s_data.get('styles', {}), s_data.get('merges', {}))

    # Read back
    state = await read_state_full(db, state_key, sheet_name, owner_id=user.id)
    return ApiResponse(data={
        'state_key': state_key,
        'cells': state.get('cells', {}),
        'styles': state.get('styles', {}),
        'merges': state.get('merges', {}),
        'col_widths': state.get('col_widths', {}),
        'row_heights': state.get('row_heights', {}),
        'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
        'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
        'all_sheets': state.get('all_sheets', ['Sheet1']),
        'sheet_set': state.get('sheet_set', {}),
    })


@router.post("/dispatch")
async def dispatch(payload: ExcelRequest, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_permission("editor"))):
    """Unified dispatch endpoint - mirrors old 表格.php API"""
    result = await _dispatch(payload.module, payload.method, payload.params,
                             payload.state_key, payload.sheet, db, owner_id=user.id)
    return ApiResponse(data=result)


@router.post("/edit")
async def edit_cell(payload: CellEditRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("editor"))):
    """Edit cell value"""
    params = {'value': payload.value}
    if payload.params:
        params.update(payload.params)
    addrs = payload.address_list or ([payload.address] if payload.address else [])
    if not addrs:
        addrs = ['A1']

    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=user.id)
    result = await EditOperations.execute(payload.method, state, payload.state_key, addrs, params)

    op_key = f'edit.{payload.method}'
    if op_key in WRITE_OPERATIONS:
        await record_snapshot(db, state, payload.state_key, op_key, addrs[0],
                              _generate_description(op_key, addrs[0], addrs, params),
                              owner_id=user.id)
        # Persist
        sheet_id = state.get('_sheet_id')
        if sheet_id:
            await sync_cells(db, sheet_id, state.get('cells', {}), state.get('styles', {}), state.get('merges', {}))

    return ApiResponse(data=result)


@router.post("/style")
async def edit_style(payload: StyleRequest, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_permission("editor"))):
    """Edit cell style"""
    addrs = payload.address_list or ['A1']
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=user.id)
    result = await StyleOperations.execute(payload.method, state, payload.state_key, addrs, payload.params)

    op_key = f'style.{payload.method}'
    if op_key in WRITE_OPERATIONS:
        await record_snapshot(db, state, payload.state_key, op_key, addrs[0],
                              _generate_description(op_key, addrs[0], addrs, payload.params),
                              owner_id=user.id)
        sheet_id = state.get('_sheet_id')
        if sheet_id:
            await sync_cells(db, sheet_id, state.get('cells', {}), state.get('styles', {}), state.get('merges', {}))

    return ApiResponse(data=result)


@router.post("/clipboard")
async def clipboard(payload: ClipboardRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("editor"))):
    """Clipboard copy/paste"""
    addrs = payload.address_list or ([payload.address] if payload.address else [])
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=user.id)
    result = await ClipboardOperations.execute(payload.method, state, payload.state_key, addrs, payload.params)
    return ApiResponse(data=result)


@router.post("/table")
async def table_op(payload: TableRequest, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_permission("editor"))):
    """Row/column operations"""
    addrs = payload.address_list or ([payload.address] if payload.address else [])
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=user.id)
    result = await RowColOperations.execute(payload.method, state, payload.state_key, addrs, payload.params)

    op_key = f'table.{payload.method}'
    if op_key in WRITE_OPERATIONS:
        await record_snapshot(db, state, payload.state_key, op_key, addrs[0] if addrs else '',
                              _generate_description(op_key, addrs[0] if addrs else '', addrs, payload.params),
                              owner_id=user.id)
        sheet_id = state.get('_sheet_id')
        if sheet_id:
            await sync_cells(db, sheet_id, state.get('cells', {}), state.get('styles', {}), state.get('merges', {}))

    return ApiResponse(data=result)


@router.post("/state")
async def state_op(payload: ExcelRequest, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_permission("editor"))):
    """State operations (undo/redo/history)"""
    if payload.method in ('archive_timeout', 'archive', 'workbook_list'):
        result = await _handle_state_direct(payload.method, payload.params, db)
    else:
        state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=user.id)
        result = await _handle_state(payload.method, state, payload.state_key, payload.params, payload.sheet, db)
    return ApiResponse(data=result)


@router.post("/export")
async def export_op(payload: ExcelRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("editor"))):
    """Export operations"""
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=user.id)
    result = await _handle_export(payload.method, state, payload.state_key, payload.sheet, payload.params, db)
    return ApiResponse(data=result)


@router.get("/download/{state_key}")
async def download_file(state_key: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_permission("viewer"))):
    """Download generated XLSX file"""
    from fastapi.responses import FileResponse
    state = await read_state_full(db, state_key, owner_id=user.id)
    result = await _handle_export('download', state, state_key, 'Sheet1', {}, db)
    if result.get('code') != 0:
        raise NotFound(result.get('msg', 'Export failed'))
    file_path = result.get('file', '')
    if not os.path.exists(file_path):
        raise NotFound('File not found')
    return FileResponse(file_path, filename=result.get('filename', 'export.xlsx'),
                        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── Register capability ──

async def _parse_capability(params: dict, caller: str) -> dict:
    """Parse XLSX/CSV capability for cross-module use"""
    file_id = int(params.get('file_id', 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    from app.config import get_settings
    from pathlib import Path
    from app.database import AsyncSessionLocal
    from app.core.exceptions import NotFound

    user_id = _resolve_user_id(caller)
    async with AsyncSessionLocal() as db:
        file = await check_file_access(db, file_id, user_id)
        ext = (file.extension or "").lower()
        if ext not in ("xlsx", "xls", "csv"):
            raise ValueError(f"Unsupported format '{ext}'")

        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()
        if os.path.commonpath([str(upload_root), str(full_path)]) != str(upload_root) or not full_path.exists():
            raise NotFound("File on disk not found")

        if ext in ("xlsx", "xls"):
            r = parse_xlsx(str(full_path), file.name)
            result = {
                'file_id': file_id, 'format': ext,
                'all_sheets': r.get('all_sheets', []),
                'sheet_set': {
                    k: {
                        'cells': v.get('cells', {}),
                        'total_rows': v.get('total_rows', DEFAULT_TOTAL_ROWS),
                        'total_cols': v.get('total_cols', DEFAULT_TOTAL_COLS),
                    }
                    for k, v in (r.get('sheet_set', {})).items()
                },
            }
        else:
            r = parse_csv(str(full_path), file.name)
            result = {
                'file_id': file_id, 'format': ext,
                'all_sheets': ['Sheet1'],
                'sheet_set': {
                    'Sheet1': {
                        'cells': r.get('cells', {}),
                        'total_rows': r.get('total_rows', DEFAULT_TOTAL_ROWS),
                        'total_cols': r.get('total_cols', DEFAULT_TOTAL_COLS),
                    }
                },
            }
    return result


register_capability(
    "excel-engine", "parse", _parse_capability,
    description="Parse XLSX/CSV files into cell data structure",
    brief="解析 Excel 数据",
    parameters={"file_id": {"type": "int"}},
    min_role="viewer",
)
