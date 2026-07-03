"""FastAPI router for excel-engine module.

1:1 translation of old 表格.php API entry + 表格_调用.php routing.
All operations go through this unified router.
"""
import io
import json
import os
from pathlib import Path

from app.config import get_settings
from app.core.exceptions import AppException, NotFound, ValidationError
from app.database import AsyncSessionLocal, get_db
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.artifact_service import create_artifact
from app.services.file_reader import resolve_caller_user_id
from app.services.file_service import check_file_access, check_file_write_access
from app.services.file_upload_service import replace_file_content, upload_file
from app.services.module_registry import register_capability
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .engine.csv_parser import parse_csv
from .engine.xlsx_generator import generate_csv, generate_xlsx
from .engine.xlsx_parser import parse_xlsx
from .init_db import _run_startup_init
from .models import ExcelVersion, ExcelWorkbook
from .state.db_ops import (
    clear_redo_stack,
    find_or_create_sheet,
    find_or_create_workbook,
    find_sheet,
    find_workbook,
    history_preview,
    read_history,
    read_state_full,
    record_snapshot,
    redo_operation,
    sync_state,
    undo_operation,
)
from .state.manager import build_snapshot, cell_set_text, empty_state, init_state, parse_addresses
from .table.clipboard import ClipboardOperations
from .table.edit import EditOperations
from .table.row_col import RowColOperations
from .table.style_ops import StyleOperations
from .tool.address import rc_to_address
from .tool.config import DEFAULT_TOTAL_COLS, DEFAULT_TOTAL_ROWS

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


def _knowledge_file_id(state_key: str) -> int | None:
    if not state_key.startswith("knowledge_"):
        return None
    raw_id = state_key.removeprefix("knowledge_")
    if not raw_id.isdigit():
        raise ValidationError("Invalid knowledge state_key")
    file_id = int(raw_id)
    if file_id <= 0:
        raise ValidationError("Invalid knowledge file id")
    return file_id


async def _resolve_state_owner_id(
    db: AsyncSession,
    state_key: str,
    user_id: int,
    *,
    write: bool = False,
) -> int:
    """Resolve the workbook owner after enforcing state_key file permissions."""
    file_id = _knowledge_file_id(state_key)
    if file_id is None:
        return user_id

    file = (
        await check_file_write_access(db, file_id, user_id)
        if write
        else await check_file_access(db, file_id, user_id)
    )
    return file.owner_id


def _is_write_operation(module: str, method: str) -> bool:
    return f"{module}.{method}" in WRITE_OPERATIONS or (
        module == "state" and method in {"undo", "redo", "archive", "archive_timeout"}
    )


def _unlink_temp_file(file_path: str | Path | None) -> None:
    if not file_path:
        return
    Path(file_path).unlink(missing_ok=True)


# Setup temp dir
_init_temp = os.path.join(os.path.dirname(__file__), '..', 'temp_files')
os.makedirs(_init_temp, exist_ok=True)
init_state(_init_temp)

router = APIRouter(prefix="/api/excel-engine", tags=["excel-engine"])
_run_startup_init()


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
    effective_owner_id = owner_id
    if state_key:
        effective_owner_id = await _resolve_state_owner_id(
            db, state_key, owner_id, write=_is_write_operation(module, method)
        )

    if module == 'load':
        return await _handle_load(method, params, db, owner_id)

    if module == 'state' and method in ('archive_timeout', 'archive', 'workbook_list'):
        return await _handle_state_direct(method, params, db, effective_owner_id)

    if load_state:
        state = await read_state_full(db, state_key, sheet, owner_id=effective_owner_id)

    addrs = parse_addresses(params)
    op_key = f'{module}.{method}'
    before_snapshot = build_snapshot(state) if op_key in WRITE_OPERATIONS else {}

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
        result = await _handle_state(method, state, state_key, params, sheet, db, effective_owner_id)
    elif module == 'export':
        result = await _handle_export(method, state, state_key, sheet, params, db, effective_owner_id)
    elif module == 'import':
        result = await _handle_import_method(method, state, state_key, params, db)

    if result is None:
        result = {'code': 1, 'msg': f'Unknown module: {module}'}

    if op_key in WRITE_OPERATIONS and result.get('code') == 0:
        workbook_id = state.get('_workbook_id') or (await find_or_create_workbook(db, state_key, owner_id=effective_owner_id))['id']
        sheet_id = state.get('_sheet_id')
        if not sheet_id:
            sheet_rec = await find_or_create_sheet(db, workbook_id, state.get('_current_sheet', sheet))
            sheet_id = sheet_rec['id']
            state['_sheet_id'] = sheet_id
        state['total_rows'] = state.get('total_rows', DEFAULT_TOTAL_ROWS)
        state['total_cols'] = state.get('total_cols', DEFAULT_TOTAL_COLS)
        await _persist_successful_write(
            db,
            state,
            state_key,
            op_key,
            addrs[0] if addrs else '',
            _generate_description(op_key, addrs[0] if addrs else '', addrs, params),
            effective_owner_id,
            before_snapshot,
        )

    if result and result.get('code') == 0:
        result.setdefault('cells', state.get('cells', {}))
        result.setdefault('styles', state.get('styles', {}))
        result.setdefault('merges', state.get('merges', {}))
        result.setdefault('col_widths', state.get('col_widths', {}))
        result.setdefault('row_heights', state.get('row_heights', {}))
        result.setdefault('total_rows', state.get('total_rows', DEFAULT_TOTAL_ROWS))
        result.setdefault('total_cols', state.get('total_cols', DEFAULT_TOTAL_COLS))
        hist_list = await read_history(db, state_key, owner_id=effective_owner_id)
        result['history_count'] = len(hist_list)

    return result


async def _handle_load(method: str, params: dict, db: AsyncSession, owner_id: int) -> dict:
    """Handle load operations"""
    if method == 'load_window':
        file_id = params.get('file_id', 0)
        state_key = f'knowledge_{file_id}'
        effective_owner_id = await _resolve_state_owner_id(db, state_key, owner_id)
        state = await read_state_full(db, state_key, owner_id=effective_owner_id)
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


async def _handle_state(method: str, state: dict, state_key: str, params: dict, sheet: str, db: AsyncSession, owner_id: int) -> dict:
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
        if not success:
            return {'code': 1, 'msg': '无可撤销操作'}
        return {'code': 0, 'msg': '', **_state_payload(state)}
    elif method == 'redo':
        success = await redo_operation(db, state, state_key)
        if not success:
            return {'code': 1, 'msg': '无可恢复操作'}
        return {'code': 0, 'msg': '', **_state_payload(state)}
    elif method == 'history_list':
        hist = await read_history(db, state_key, owner_id=owner_id)
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


async def _handle_state_direct(method: str, params: dict, db: AsyncSession, owner_id: int) -> dict:
    if method == 'workbook_list':
        result = await db.execute(
            text(f"SELECT id, name, upload_time FROM {ExcelWorkbook.__tablename__} WHERE owner_id = :owner_id ORDER BY last_active_time DESC"),
            {"owner_id": owner_id},
        )
        items = [{'id': r[0], 'name': r[1], 'upload_time': str(r[2])} for r in result.fetchall()]
        return {'code': 0, 'workbooks': items}
    return {'code': 1, 'msg': f'Unknown direct state method: {method}'}


async def _handle_export(
    method: str,
    state: dict,
    state_key: str,
    sheet: str,
    params: dict,
    db: AsyncSession,
    owner_id: int = 0,
) -> dict:
    import tempfile

    if method == 'download':
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

        fd, tmp_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        try:
            success = generate_xlsx(tmp_path, all_sheet_data)
        except Exception:
            _unlink_temp_file(tmp_path)
            raise
        if not success:
            _unlink_temp_file(tmp_path)
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
        fd, tmp_path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            csv_content = generate_csv(tmp_path, state, sheet)
            return {'code': 0, 'csv': csv_content}
        finally:
            _unlink_temp_file(tmp_path)
    elif method == 'save_version':
        version = await _save_version_record(db, state_key, state, owner_id, params.get('version_name'))
        return {'code': 0, 'version': version}
    return {'code': 1, 'msg': f'Unknown export method: {method}'}


async def _handle_import_method(method: str, state: dict, state_key: str, params: dict, db: AsyncSession) -> dict:
    return {'code': 1, 'msg': f'Unknown import method: {method}'}


def _legacy_result_to_api(result: dict) -> ApiResponse:
    """Wrap a legacy {code, msg} result into ApiResponse with correct success/error semantics.

    Legacy internal results use {code: 0, msg} for success and {code: 1, msg} for failure.
    This ensures the outer ApiResponse doesn't hide failures behind success:true.
    """
    if isinstance(result, dict) and result.get("code") not in (None, 0):
        return ApiResponse(
            success=False,
            data=None,
            error=result.get("msg", "Operation failed"),
        )
    return ApiResponse(data=result)


async def _sync_sheet_data(db: AsyncSession, sheet_id: int, sheet_data: dict) -> None:
    await sync_state(db, sheet_id, sheet_data)


def _state_payload(state: dict) -> dict:
    return {
        'cells': state.get('cells', {}),
        'styles': state.get('styles', {}),
        'merges': state.get('merges', {}),
        'col_widths': state.get('col_widths', {}),
        'row_heights': state.get('row_heights', {}),
        'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
        'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
    }


async def _save_version_record(
    db: AsyncSession,
    state_key: str,
    state: dict,
    owner_id: int,
    version_name: str | None = None,
) -> dict:
    file_id = _knowledge_file_id(state_key)
    if file_id is None:
        raise ValidationError("Versions require a knowledge file state_key")
    snapshot_json = json.dumps(build_snapshot(state), ensure_ascii=False)
    version = ExcelVersion(
        file_id=file_id,
        version_name=version_name or f"{state_key} manual",
        file_size=len(snapshot_json.encode("utf-8")),
        snapshot_json=snapshot_json,
        operation_steps=len(await read_history(db, state_key, owner_id=owner_id)),
        creator_id=owner_id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return {
        "id": version.id,
        "version_name": version.version_name,
        "file_size": version.file_size,
        "operation_steps": version.operation_steps,
        "created_at": version.created_at.isoformat() if version.created_at else "",
    }


async def _persist_successful_write(
    db: AsyncSession,
    state: dict,
    state_key: str,
    action: str,
    addr: str,
    description: str,
    owner_id: int,
    before_snapshot: dict,
) -> None:
    sheet_id = state.get('_sheet_id')
    if not sheet_id:
        return
    await record_snapshot(
        db,
        state,
        state_key,
        action,
        addr,
        description,
        owner_id=owner_id,
        snapshot=before_snapshot,
    )
    await clear_redo_stack(db, sheet_id)
    await sync_state(db, sheet_id, state)


# ── API Endpoints ──

@router.get("/health")
async def health():
    return ApiResponse(data={"module": "excel-engine", "status": "ok"})


@router.post("/parse")
async def parse_xlsx_file(payload: OpenRequest, db: AsyncSession = Depends(get_db),
                          user: User = Depends(require_permission("viewer"))):
    """Parse XLSX/CSV file from file storage"""
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

    return _legacy_result_to_api(result)


@router.post("/open")
async def open_xlsx(payload: OpenRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("viewer"))):
    """Open XLSX file - loads into DB state and returns initialized state"""
    file = await check_file_access(db, payload.file_id, user.id)
    ext = (file.extension or "").lower()
    state_key = f'knowledge_{payload.file_id}'
    state_owner_id = file.owner_id

    # Check if already loaded
    existing = await find_workbook(db, state_key, owner_id=state_owner_id)
    if existing:
        state = await read_state_full(db, state_key, payload.target_sheet or 'Sheet1', owner_id=state_owner_id)
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
        raise ValidationError("Unsupported format")

    if result.get('code') != 0:
        raise AppException(result.get('msg', 'Parse failed'))

    wb = await find_or_create_workbook(db, state_key, owner_id=state_owner_id)
    sheet_name = payload.target_sheet or (result.get('all_sheets', ['Sheet1'])[0])

    if 'sheet_set' in result:
        for s_name, s_data in result['sheet_set'].items():
            sheet_rec = await find_or_create_sheet(
                db, wb['id'], s_name, s_data.get('total_rows', DEFAULT_TOTAL_ROWS), s_data.get('total_cols', DEFAULT_TOTAL_COLS)
            )
            await _sync_sheet_data(db, sheet_rec['id'], s_data)

    # Read back
    state = await read_state_full(db, state_key, sheet_name, owner_id=state_owner_id)
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
    return _legacy_result_to_api(result)


@router.post("/edit")
async def edit_cell(payload: CellEditRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("editor"))):
    """Edit cell value"""
    state_owner_id = await _resolve_state_owner_id(db, payload.state_key, user.id, write=True)
    params = {'value': payload.value}
    if payload.params:
        params.update(payload.params)
    addrs = payload.address_list or ([payload.address] if payload.address else [])
    if not addrs:
        addrs = ['A1']

    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=state_owner_id)
    before_snapshot = build_snapshot(state)
    result = await EditOperations.execute(payload.method, state, payload.state_key, addrs, params)

    op_key = f'edit.{payload.method}'
    if op_key in WRITE_OPERATIONS and result.get('code') == 0:
        await _persist_successful_write(
            db, state, payload.state_key, op_key, addrs[0],
            _generate_description(op_key, addrs[0], addrs, params),
            state_owner_id, before_snapshot,
        )
        result.update(_state_payload(state))

    return _legacy_result_to_api(result)


@router.post("/style")
async def edit_style(payload: StyleRequest, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_permission("editor"))):
    """Edit cell style"""
    state_owner_id = await _resolve_state_owner_id(db, payload.state_key, user.id, write=True)
    addrs = payload.address_list or ['A1']
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=state_owner_id)
    before_snapshot = build_snapshot(state)
    result = await StyleOperations.execute(payload.method, state, payload.state_key, addrs, payload.params)

    op_key = f'style.{payload.method}'
    if op_key in WRITE_OPERATIONS and result.get('code') == 0:
        await _persist_successful_write(
            db, state, payload.state_key, op_key, addrs[0],
            _generate_description(op_key, addrs[0], addrs, payload.params),
            state_owner_id, before_snapshot,
        )
        result.update(_state_payload(state))

    return _legacy_result_to_api(result)


@router.post("/clipboard")
async def clipboard(payload: ClipboardRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("editor"))):
    """Clipboard copy/paste"""
    addrs = payload.address_list or ([payload.address] if payload.address else [])
    state_owner_id = await _resolve_state_owner_id(
        db, payload.state_key, user.id, write=f"clipboard.{payload.method}" in WRITE_OPERATIONS
    )
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=state_owner_id)
    before_snapshot = build_snapshot(state)
    result = await ClipboardOperations.execute(payload.method, state, payload.state_key, addrs, payload.params)
    op_key = f'clipboard.{payload.method}'
    if op_key in WRITE_OPERATIONS and result.get('code') == 0:
        target_addr = addrs[0] if addrs else payload.address
        await _persist_successful_write(
            db, state, payload.state_key, op_key, target_addr,
            _generate_description(op_key, target_addr, addrs, payload.params),
            state_owner_id, before_snapshot,
        )
        result.update(_state_payload(state))
    return _legacy_result_to_api(result)


@router.post("/table")
async def table_op(payload: TableRequest, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_permission("editor"))):
    """Row/column operations"""
    state_owner_id = await _resolve_state_owner_id(db, payload.state_key, user.id, write=True)
    addrs = payload.address_list or ([payload.address] if payload.address else [])
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=state_owner_id)
    before_snapshot = build_snapshot(state)
    result = await RowColOperations.execute(payload.method, state, payload.state_key, addrs, payload.params)

    op_key = f'table.{payload.method}'
    if op_key in WRITE_OPERATIONS and result.get('code') == 0:
        target_addr = addrs[0] if addrs else ''
        await _persist_successful_write(
            db, state, payload.state_key, op_key, target_addr,
            _generate_description(op_key, target_addr, addrs, payload.params),
            state_owner_id, before_snapshot,
        )
        result.update(_state_payload(state))

    return _legacy_result_to_api(result)


@router.post("/state")
async def state_op(payload: ExcelRequest, db: AsyncSession = Depends(get_db),
                   user: User = Depends(require_permission("editor"))):
    """State operations (undo/redo/history)"""
    is_write = _is_write_operation("state", payload.method)
    state_owner_id = await _resolve_state_owner_id(db, payload.state_key, user.id, write=is_write) if payload.state_key else user.id
    if payload.method in ('archive_timeout', 'archive', 'workbook_list'):
        result = await _handle_state_direct(payload.method, payload.params, db, state_owner_id)
    else:
        state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=state_owner_id)
        result = await _handle_state(payload.method, state, payload.state_key, payload.params, payload.sheet, db, state_owner_id)
    return _legacy_result_to_api(result)


@router.post("/export")
async def export_op(payload: ExcelRequest, db: AsyncSession = Depends(get_db),
                    user: User = Depends(require_permission("editor"))):
    """Export operations"""
    state_owner_id = await _resolve_state_owner_id(db, payload.state_key, user.id)
    state = await read_state_full(db, payload.state_key, payload.sheet, owner_id=state_owner_id)
    result = await _handle_export(payload.method, state, payload.state_key, payload.sheet, payload.params, db, state_owner_id)
    return _legacy_result_to_api(result)


@router.get("/download/{state_key}")
async def download_file(state_key: str, db: AsyncSession = Depends(get_db),
                        user: User = Depends(require_permission("viewer"))):
    """Download generated XLSX file"""
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    state_owner_id = await _resolve_state_owner_id(db, state_key, user.id)
    state = await read_state_full(db, state_key, owner_id=state_owner_id)
    result = await _handle_export('download', state, state_key, 'Sheet1', {}, db, state_owner_id)
    if result.get('code') != 0:
        raise NotFound(result.get('msg', 'Export failed'))
    file_path = result.get('file', '')
    if not os.path.exists(file_path):
        raise NotFound('File not found')
    return FileResponse(file_path, filename=result.get('filename', 'export.xlsx'),
                        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        background=BackgroundTask(_unlink_temp_file, file_path))


# ── Cross-module capabilities ──

async def _parse_capability(params: dict, caller: str) -> dict:
    """Parse XLSX/CSV files into cell data structure"""
    file_id = int(params.get('file_id', 0))
    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    user_id = resolve_caller_user_id(caller)
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
            if r.get('code') != 0:
                raise ValueError(r.get('msg', 'Parse failed'))
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


async def _create_workbook_capability(params: dict, caller: str) -> dict:
    """Create a new empty workbook in the database."""
    from app.database import AsyncSessionLocal

    user_id = resolve_caller_user_id(caller)
    from datetime import datetime
    name = params.get("name", "Untitled")
    state_key = params.get("state_key", f"wb_{user_id}_{int(datetime.utcnow().timestamp())}")

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id, write=True)
        wb = await find_or_create_workbook(db, state_key, owner_id=state_owner_id)
        await db.execute(
            text(f"UPDATE {ExcelWorkbook.__tablename__} SET name = :name WHERE id = :id"),
            {"name": name, "id": wb["id"]},
        )
        await db.commit()
        wb["name"] = name
        sheet = await find_or_create_sheet(db, wb['id'], 'Sheet1')
        state = empty_state()
        state['_workbook_id'] = wb['id']
        state['_sheet_id'] = sheet['id']
        await sync_state(db, sheet['id'], state)

    return {
        'state_key': state_key,
        'workbook_id': wb['id'],
        'sheet_id': sheet['id'],
        'name': name,
        'total_rows': DEFAULT_TOTAL_ROWS,
        'total_cols': DEFAULT_TOTAL_COLS,
    }


async def _import_file_to_workbook_capability(params: dict, caller: str) -> dict:
    """Import a file into a database workbook."""
    user_id = resolve_caller_user_id(caller)
    file_id = int(params.get('file_id', 0))
    state_key = params.get('state_key', f'knowledge_{file_id}')

    if file_id <= 0:
        raise ValueError("file_id must be a positive integer")

    async with AsyncSessionLocal() as db:
        state_file_id = _knowledge_file_id(state_key)
        file = (
            await check_file_write_access(db, file_id, user_id)
            if state_file_id == file_id
            else await check_file_access(db, file_id, user_id)
        )
        state_owner_id = file.owner_id if state_file_id == file_id else user_id
        ext = (file.extension or "").lower()
        upload_root = Path(get_settings().UPLOAD_DIR).resolve()
        full_path = (upload_root / file.storage_path).resolve()

        if ext in ("xlsx", "xls"):
            result = parse_xlsx(str(full_path), file.name)
        elif ext == "csv":
            result = parse_csv(str(full_path), file.name)
        else:
            raise ValueError(f"Unsupported format: {ext}")

        if result.get('code') != 0:
            raise ValueError(result.get('msg', 'Parse failed'))

        wb = await find_or_create_workbook(db, state_key, owner_id=state_owner_id)

        if 'sheet_set' in result:
            for s_name, s_data in result['sheet_set'].items():
                sheet_rec = await find_or_create_sheet(
                    db, wb['id'], s_name,
                    s_data.get('total_rows', DEFAULT_TOTAL_ROWS),
                    s_data.get('total_cols', DEFAULT_TOTAL_COLS),
                )
                await _sync_sheet_data(db, sheet_rec['id'], s_data)

        state = await read_state_full(db, state_key, owner_id=state_owner_id)

    return {
        'state_key': state_key,
        'workbook_id': wb['id'],
        'file_id': file_id,
        'all_sheets': state.get('all_sheets', ['Sheet1']),
        'total_rows': state.get('total_rows', DEFAULT_TOTAL_ROWS),
        'total_cols': state.get('total_cols', DEFAULT_TOTAL_COLS),
    }


async def _update_range_capability(params: dict, caller: str) -> dict:
    """Update a range of cells in the workbook."""
    from app.database import AsyncSessionLocal

    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')
    sheet = params.get('sheet', 'Sheet1')
    rows_data = params.get('rows', [])

    if not state_key:
        raise ValueError("state_key is required")
    if not rows_data:
        raise ValueError("rows data is required")

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id, write=True)
        state = await read_state_full(db, state_key, sheet, owner_id=state_owner_id)
        before_snapshot = build_snapshot(state)

        start_col = params.get('start_col', 0)
        start_row = params.get('start_row', 0)

        for ri, row in enumerate(rows_data):
            for ci, val in enumerate(row):
                addr = rc_to_address(start_row + ri + 1, start_col + ci)
                cell_set_text(state, addr, str(val) if val is not None else '')
        max_width = max((len(row) for row in rows_data), default=0)
        state['total_rows'] = max(state.get('total_rows', DEFAULT_TOTAL_ROWS), start_row + len(rows_data))
        state['total_cols'] = max(state.get('total_cols', DEFAULT_TOTAL_COLS), start_col + max_width)

        sheet_id = state.get('_sheet_id')
        if sheet_id:
            await _persist_successful_write(
                db,
                state,
                state_key,
                'edit.input',
                rc_to_address(start_row + 1, start_col),
                f'Update range {len(rows_data)} rows',
                state_owner_id,
                before_snapshot,
            )

    return {
        'state_key': state_key,
        'rows_updated': len(rows_data),
        'total_cells': len(state.get('cells', {})),
    }


async def _append_rows_capability(params: dict, caller: str) -> dict:
    """Append rows to the end of a sheet."""
    from app.database import AsyncSessionLocal

    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')
    sheet = params.get('sheet', 'Sheet1')
    rows_data = params.get('rows', [])

    if not state_key:
        raise ValueError("state_key is required")
    if not rows_data:
        raise ValueError("rows data is required")

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id, write=True)
        state = await read_state_full(db, state_key, sheet, owner_id=state_owner_id)
        before_snapshot = build_snapshot(state)

        import re
        current_cells = state.get('cells', {})
        max_row = 0
        for addr in current_cells:
            m = re.match(r'([A-Z]+)(\d+)', addr)
            if m:
                max_row = max(max_row, int(m.group(2)))

        start_row = max_row + 1
        for ri, row in enumerate(rows_data):
            for ci, val in enumerate(row):
                addr = rc_to_address(start_row + ri, ci)
                cell_set_text(state, addr, str(val) if val is not None else '')
        max_width = max((len(row) for row in rows_data), default=0)
        state['total_rows'] = max(state.get('total_rows', DEFAULT_TOTAL_ROWS), start_row + len(rows_data) - 1)
        state['total_cols'] = max(state.get('total_cols', DEFAULT_TOTAL_COLS), max_width)

        sheet_id = state.get('_sheet_id')
        if sheet_id:
            await _persist_successful_write(
                db,
                state,
                state_key,
                'edit.input',
                f'A{start_row}',
                f'Append {len(rows_data)} rows starting at row {start_row}',
                state_owner_id,
                before_snapshot,
            )

    return {
        'state_key': state_key,
        'rows_appended': len(rows_data),
        'start_row': start_row,
        'total_cells': len(state.get('cells', {})),
    }


async def _undo_capability(params: dict, caller: str) -> dict:
    """Undo the last operation."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id, write=True)
        state = await read_state_full(db, state_key, owner_id=state_owner_id)
        success = await undo_operation(db, state, state_key)

    return {
        'state_key': state_key,
        'success': success,
        'message': '' if success else 'No operations to undo',
        **(_state_payload(state) if success else {}),
    }


async def _redo_capability(params: dict, caller: str) -> dict:
    """Redo the last undone operation."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id, write=True)
        state = await read_state_full(db, state_key, owner_id=state_owner_id)
        success = await redo_operation(db, state, state_key)

    return {
        'state_key': state_key,
        'success': success,
        'message': '' if success else 'No operations to redo',
        **(_state_payload(state) if success else {}),
    }


async def _list_history_capability(params: dict, caller: str) -> dict:
    """List operation history for a workbook."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id)
        history = await read_history(db, state_key, owner_id=state_owner_id)

    return {
        'state_key': state_key,
        'history': history,
        'total': len(history),
    }


async def _list_versions_capability(params: dict, caller: str) -> dict:
    """List saved versions of a workbook."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')
    file_id = _knowledge_file_id(state_key)
    if file_id is None:
        return {'state_key': state_key, 'versions': []}

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id)
        wb = await find_workbook(db, state_key, owner_id=state_owner_id)
        if not wb:
            return {'state_key': state_key, 'versions': []}

        result = await db.execute(
            text(f"SELECT id, version_name, file_size, operation_steps, created_at "
                 f"FROM {ExcelVersion.__tablename__} "
                 f"WHERE file_id = :file_id AND creator_id IN (0, :owner_id) "
                 f"ORDER BY id DESC"),
            {"file_id": file_id, "owner_id": state_owner_id},
        )
        versions = []
        for r in result.fetchall():
            versions.append({
                'id': r[0],
                'version_name': r[1],
                'file_size': r[2],
                'operation_steps': r[3],
                'created_at': str(r[4]) if r[4] else '',
            })

    return {'state_key': state_key, 'versions': versions}


async def _restore_version_capability(params: dict, caller: str) -> dict:
    """Restore a workbook to a saved version."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')
    version_id = int(params.get('version_id', 0))
    file_id = _knowledge_file_id(state_key)
    if file_id is None:
        raise ValueError("Versions can only be restored for knowledge file state")

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id, write=True)
        wb = await find_workbook(db, state_key, owner_id=state_owner_id)
        if not wb:
            raise ValueError(f"Workbook not found: {state_key}")

        result = await db.execute(
            text(f"SELECT snapshot_json FROM {ExcelVersion.__tablename__} "
                 f"WHERE id = :vid AND file_id = :file_id AND creator_id IN (0, :owner_id)"),
            {'vid': version_id, 'file_id': file_id, 'owner_id': state_owner_id},
        )
        row = result.fetchone()
        if not row:
            raise ValueError("Version not found")

        snapshot = json.loads(row[0]) if row[0] else empty_state()
        restored_state = {}
        if isinstance(snapshot, dict):
            sheet_rec = await find_sheet(db, wb['id'], params.get('sheet', 'Sheet1'))
            if sheet_rec:
                await sync_state(db, sheet_rec['id'], snapshot)
                restored_state = await read_state_full(db, state_key, params.get('sheet', 'Sheet1'), owner_id=state_owner_id)

    return {'state_key': state_key, 'version_id': version_id, 'restored': True, **_state_payload(restored_state)}


async def _export_xlsx_capability(params: dict, caller: str) -> dict:
    """Export workbook to XLSX file."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')
    sheet = params.get('sheet', 'Sheet1')
    folder_id = params.get('folder_id')
    temp_path: Path | None = None

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id)
        state = await read_state_full(db, state_key, sheet, owner_id=state_owner_id)

        result = await _handle_export('download', state, state_key, sheet, {}, db, state_owner_id)
        if result.get('code') != 0:
            raise ValueError(result.get('msg', 'Export failed'))

        file_path = result.get('file', '')
        temp_path = Path(file_path)
        if not temp_path.exists():
            raise ValueError("Export file not found")

        try:
            content_bytes = temp_path.read_bytes()
            upload_result = await upload_file(
                db, io.BytesIO(content_bytes),
                f"{state_key}.xlsx", user_id, folder_id,
            )
            wb = await find_workbook(db, state_key, owner_id=state_owner_id)
            artifact = await create_artifact(
                db,
                user_id,
                name=state_key,
                extension="xlsx",
                content=content_bytes,
                folder_id=folder_id,
                source_module="excel-engine",
                source_object_type="workbook",
                source_object_id=wb['id'] if wb else None,
                file_id=upload_result['id'],
                conflict_policy="auto_rename",
            )
        finally:
            _unlink_temp_file(temp_path)

    return {
        'file_id': upload_result['id'],
        'artifact_id': artifact['id'],
        'name': upload_result['name'],
        'extension': upload_result['extension'],
        'size': upload_result['size'],
        'state_key': state_key,
    }


async def _publish_to_desktop_capability(params: dict, caller: str) -> dict:
    """Publish workbook to desktop — export to XLSX and publish/replace desktop file."""
    user_id = resolve_caller_user_id(caller)
    state_key = params.get('state_key', '')
    sheet = params.get('sheet', 'Sheet1')
    target_file_id = params.get('target_file_id')
    temp_path: Path | None = None

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id)
        state = await read_state_full(db, state_key, sheet, owner_id=state_owner_id)

        result = await _handle_export('download', state, state_key, sheet, {}, db, state_owner_id)
        if result.get('code') != 0:
            raise ValueError(result.get('msg', 'Export failed'))

        file_path = result.get('file', '')
        temp_path = Path(file_path)
        if not temp_path.exists():
            raise ValueError("Export file not found")

        try:
            content_bytes = temp_path.read_bytes()
            wb = await find_workbook(db, state_key, owner_id=state_owner_id)

            if target_file_id:
                file_result = await replace_file_content(db, int(target_file_id), user_id, content_bytes)
                artifact_name = file_result.get('name') or state_key
            else:
                wb_name = wb['name'] if wb else state_key
                file_result = await upload_file(
                    db, io.BytesIO(content_bytes),
                    f"{wb_name}.xlsx", user_id, params.get('folder_id'),
                )
                artifact_name = file_result.get('name') or wb_name

            artifact = await create_artifact(
                db,
                user_id,
                name=artifact_name,
                extension='xlsx',
                content=content_bytes,
                folder_id=params.get('folder_id'),
                source_module='excel-engine',
                source_object_type='workbook',
                source_object_id=wb['id'] if wb else None,
                file_id=file_result.get('id', file_result.get('file_id')),
                conflict_policy='auto_rename',
            )
        finally:
            _unlink_temp_file(temp_path)

    return {
        'file_id': file_result.get('id', file_result.get('file_id')),
        'artifact_id': artifact['id'],
        'name': file_result.get('name'),
        'size': file_result.get('size'),
        'state_key': state_key,
        'published': True,
    }


register_capability(
    "excel-engine", "parse", _parse_capability,
    description="Parse XLSX/CSV files into cell data structure",
    brief="解析 Excel 数据",
    parameters={"file_id": {"type": "int"}},
    min_role="viewer",
)

register_capability(
    "excel-engine", "create_workbook", _create_workbook_capability,
    description="Create a new empty workbook in the database.",
    brief="创建工作簿",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Workbook name", "default": "Untitled"},
            "state_key": {"type": "string", "description": "Optional state_key (auto-generated if omitted)"},
        },
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "import_file_to_workbook", _import_file_to_workbook_capability,
    description="Import a file into a database workbook for editing.",
    brief="导入文件到工作簿",
    parameters={
        "type": "object",
        "properties": {
            "file_id": {"type": "integer", "description": "File ID to import"},
            "state_key": {"type": "string", "description": "Optional state_key"},
        },
        "required": ["file_id"],
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "update_range", _update_range_capability,
    description="Update a range of cells starting at a given position.",
    brief="更新单元格范围",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
            "sheet": {"type": "string", "description": "Sheet name", "default": "Sheet1"},
            "start_row": {"type": "integer", "description": "Starting row (0-based)", "default": 0},
            "start_col": {"type": "integer", "description": "Starting column (0-based)", "default": 0},
            "rows": {"type": "array", "description": "2D array of cell values"},
        },
        "required": ["state_key", "rows"],
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "append_rows", _append_rows_capability,
    description="Append rows to the end of a sheet.",
    brief="追加行",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
            "sheet": {"type": "string", "description": "Sheet name", "default": "Sheet1"},
            "rows": {"type": "array", "description": "2D array of cell values to append"},
        },
        "required": ["state_key", "rows"],
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "undo", _undo_capability,
    description="Undo the last operation.",
    brief="撤销",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
        },
        "required": ["state_key"],
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "redo", _redo_capability,
    description="Redo the last undone operation.",
    brief="重做",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
        },
        "required": ["state_key"],
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "list_history", _list_history_capability,
    description="List operation history for a workbook.",
    brief="列出操作历史",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
        },
        "required": ["state_key"],
    },
    min_role="viewer",
)

register_capability(
    "excel-engine", "list_versions", _list_versions_capability,
    description="List saved versions of a workbook.",
    brief="列出版本",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
        },
        "required": ["state_key"],
    },
    min_role="viewer",
)

register_capability(
    "excel-engine", "restore_version", _restore_version_capability,
    description="Restore a workbook to a saved version.",
    brief="恢复版本",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
            "version_id": {"type": "integer", "description": "Version ID to restore"},
        },
        "required": ["state_key", "version_id"],
    },
    min_role="editor",
)

async def _compile_xlsx_capability(params: dict, caller: str) -> dict:
    """Compile workbook cells to a temporary XLSX file for download.

    Does NOT create framework_file_items or artifacts.
    Returns temp file path; caller is responsible for cleanup.
    """
    import tempfile
    from pathlib import Path

    user_id = resolve_caller_user_id(caller)
    state_key = params.get("state_key", "")
    sheet = params.get("sheet", "Sheet1")

    if not state_key:
        return {"success": False, "error": "state_key required"}

    async with AsyncSessionLocal() as db:
        state_owner_id = await _resolve_state_owner_id(db, state_key, user_id)
        workbook = await find_workbook(db, state_key, owner_id=state_owner_id)
        if not workbook:
            return {"success": False, "error": f"Workbook not found: {state_key}"}

        state = await read_state_full(db, state_key, sheet, owner_id=state_owner_id)

        result = await _handle_export('download', state, state_key, sheet, {}, db, state_owner_id)
        if result.get('code') != 0:
            return {"success": False, "error": result.get('msg', 'Export failed')}

        file_path = result.get('file', '')
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": "Export file not found"}

        filename = result.get('filename', 'export.xlsx')
        file_path_obj = Path(file_path).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if os.path.commonpath([str(temp_root), str(file_path_obj)]) != str(temp_root):
            return {"success": False, "error": "Invalid compile output path"}
        if "/" in filename or "\\" in filename:
            return {"success": False, "error": "Invalid filename"}

    return {
        "file_path": str(file_path_obj),
        "filename": filename,
        "state_key": state_key,
    }


register_capability(
    "excel-engine", "compile_xlsx", _compile_xlsx_capability,
    description="Compile workbook to temporary XLSX for download (no file record created).",
    brief="编译 XLSX 临时下载",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
            "sheet": {"type": "string", "description": "Sheet name", "default": "Sheet1"},
        },
        "required": ["state_key"],
    },
    min_role="viewer",
)

register_capability(
    "excel-engine", "export_xlsx", _export_xlsx_capability,
    description="Export workbook to XLSX file in the file system.",
    brief="导出 XLSX",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
            "sheet": {"type": "string", "description": "Sheet name", "default": "Sheet1"},
            "folder_id": {"type": "integer", "description": "Target folder ID (optional)"},
        },
        "required": ["state_key"],
    },
    min_role="editor",
)

register_capability(
    "excel-engine", "publish_to_desktop", _publish_to_desktop_capability,
    description="Publish workbook to desktop — export to XLSX and replace/create desktop file.",
    brief="发布到桌面",
    parameters={
        "type": "object",
        "properties": {
            "state_key": {"type": "string", "description": "Workbook state_key"},
            "sheet": {"type": "string", "description": "Sheet name", "default": "Sheet1"},
            "target_file_id": {"type": "integer", "description": "Target desktop file ID (optional, creates new if omitted)"},
            "folder_id": {"type": "integer", "description": "Target folder ID (optional)"},
        },
        "required": ["state_key"],
    },
    min_role="editor",
)
