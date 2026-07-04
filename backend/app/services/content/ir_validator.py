"""Content IR validator — schema + semantic profile validation.

Two-layer validation:
  1. Schema validation: JSON structure, required fields, block types.
  2. Semantic (profile) validation: content_type-specific rules.
"""
import logging
from typing import Any

from app.services.content.ir_schema import (
    BLOCK_TYPE_VALUES,
    CONTENT_TYPE_PROFILES,
    CONTENT_TYPE_VALUES,
    ValidationResult,
)
from app.services.content.ir_schema import (
    ValidationError as IRValidationError,
)

logger = logging.getLogger("v2.content").getChild("ir_validator")


async def validate_ir(content_ir: dict[str, Any]) -> ValidationResult:
    """Validate a Content IR dict. Returns structured result (never raises)."""
    errors: list[IRValidationError] = []

    # Layer 1: Schema validation
    _validate_schema(content_ir, errors)

    if errors:
        return ValidationResult(valid=False, errors=errors)

    # Layer 2: Semantic profile validation
    content_type = content_ir.get("content_type", "")
    _validate_profile(content_ir, content_type, errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def _validate_schema(ir: dict[str, Any], errors: list[IRValidationError]) -> None:
    """Check JSON structure basics."""
    # Required top-level fields
    for field in ("schema_version", "content_type", "title", "blocks"):
        if field not in ir:
            errors.append(IRValidationError(
                path=field,
                code="missing_required_field",
                message=f"Missing required field: {field}",
            ))

    if errors:
        return

    # content_type must be valid enum
    ct = ir.get("content_type", "")
    if ct not in CONTENT_TYPE_VALUES:
        expected_list = " | ".join(sorted(CONTENT_TYPE_VALUES))
        errors.append(IRValidationError(
            path="content_type",
            code="invalid_content_type",
            message=f"Invalid content_type: {ct}",
            expected=expected_list,
            actual=ct,
        ))

    # blocks must be list
    blocks = ir.get("blocks")
    if not isinstance(blocks, list):
        errors.append(IRValidationError(
            path="blocks",
            code="invalid_type",
            message="blocks must be an array",
            expected="array",
            actual=type(blocks).__name__,
        ))
        return

    # resources/assets/warnings/quality must keep the canonical reference shape.
    resources = ir.get("resources")
    if resources is not None and not isinstance(resources, list):
        errors.append(IRValidationError(
            path="resources",
            code="invalid_type",
            message="resources must be an array",
            expected="array",
            actual=type(resources).__name__,
        ))
    assets = ir.get("assets")
    if assets is not None and not isinstance(assets, list):
        errors.append(IRValidationError(
            path="assets",
            code="invalid_type",
            message="assets must be an array",
            expected="array",
            actual=type(assets).__name__,
        ))
    warnings = ir.get("warnings")
    if warnings is not None and not isinstance(warnings, list):
        errors.append(IRValidationError(
            path="warnings",
            code="invalid_type",
            message="warnings must be an array",
            expected="array",
            actual=type(warnings).__name__,
        ))
    quality = ir.get("quality")
    if quality is not None and not isinstance(quality, dict):
        errors.append(IRValidationError(
            path="quality",
            code="invalid_type",
            message="quality must be an object",
            expected="object",
            actual=type(quality).__name__,
        ))

    # Validate block types recursively
    if isinstance(blocks, list):
        resource_items = resources if isinstance(resources, list) else assets
        resource_ids: set[str | int] = set()
        if isinstance(resource_items, list):
            for r in resource_items:
                if not isinstance(r, dict):
                    continue
                rid = r.get("id")
                if rid is not None:
                    if rid in resource_ids:
                        errors.append(IRValidationError(
                            path="resources",
                            code="duplicate_resource_id",
                            message=f"Duplicate resource id: {rid}",
                            actual=str(rid),
                        ))
                    resource_ids.add(rid)

        _validate_blocks(blocks, errors, "blocks")


def _validate_blocks(
    blocks: list[Any], errors: list[IRValidationError],
    path_prefix: str = "",
) -> None:
    for idx, block in enumerate(blocks):
        path = f"{path_prefix}[{idx}]"
        if not isinstance(block, dict):
            errors.append(IRValidationError(
                path=path,
                code="invalid_block_type",
                message="Each block must be a JSON object",
                expected="object",
                actual=type(block).__name__,
            ))
            continue

        btype = block.get("type", "")
        if not btype:
            errors.append(IRValidationError(
                path=f"{path}.type",
                code="missing_block_type",
                message="Block missing type field",
            ))
        elif btype not in BLOCK_TYPE_VALUES:
            expected_list = " | ".join(sorted(BLOCK_TYPE_VALUES))
            errors.append(IRValidationError(
                path=f"{path}.type",
                code="unsupported_block_type",
                message=f"Unsupported block type: {btype}",
                expected=expected_list,
                actual=btype,
            ))

        # Validate children recursively
        children = block.get("children")
        if isinstance(children, list) and children:
            _validate_blocks(children, errors, f"{path}.children")


def _validate_profile(
    ir: dict[str, Any], content_type: str,
    errors: list[IRValidationError],
) -> None:
    """Validate content_type-specific semantic rules."""
    profile = CONTENT_TYPE_PROFILES.get(content_type)
    if not profile:
        return

    blocks = ir.get("blocks", [])
    resources = ir.get("resources", ir.get("assets", []))

    # Image must have image block or resource
    if content_type == "image":
        has_image_block = any(
            b.get("type") == "image" for b in blocks
        )
        has_resource = isinstance(resources, list) and len(resources) > 0
        if not has_image_block and not has_resource:
            errors.append(IRValidationError(
                path="blocks",
                code="image_no_content",
                message="Image content_type must have at least one image block or resource",
            ))

    # Memory forbids binary-large fields
    if content_type == "memory":
        for idx, block in enumerate(blocks):
            if block.get("style"):
                errors.append(IRValidationError(
                    path=f"blocks[{idx}].style",
                    code="memory_no_style",
                    message="Memory blocks must not have style fields",
                ))

    # Presentation: top-level must be slide; no slide-nesting; slide children restricted
    if content_type == "presentation":
        allowed_in_slide = profile.get("allowed_nested_in_slide", set())
        for idx, block in enumerate(blocks):
            btype = block.get("type", "")
            if btype != "slide":
                errors.append(IRValidationError(
                    path=f"blocks[{idx}].type",
                    code="presentation_needs_slide",
                    message="Top-level blocks in presentation must be slides",
                    expected="slide",
                    actual=btype,
                ))
            # Check slide children are allowed types
            children = block.get("children", [])
            if isinstance(children, list):
                for ci, child in enumerate(children):
                    if isinstance(child, dict) and child.get("type") == "slide":
                        errors.append(IRValidationError(
                            path=f"blocks[{idx}].children[{ci}].type",
                            code="slide_nested_slide",
                            message="Slides must not nest other slides",
                            expected="non-slide block type",
                            actual="slide",
                        ))
                    elif isinstance(child, dict) and allowed_in_slide and child.get("type") not in allowed_in_slide:
                        errors.append(IRValidationError(
                            path=f"blocks[{idx}].children[{ci}].type",
                            code="unsupported_block_in_slide",
                            message=f"Block type '{child.get('type')}' not allowed inside slide",
                            expected=" | ".join(sorted(allowed_in_slide)),
                            actual=child.get("type", ""),
                        ))

    # Spreadsheet: top-level must be sheet; sheet children validated
    if content_type == "spreadsheet":
        allowed_in_sheet = profile.get("allowed_nested_in_sheet", set())
        for idx, block in enumerate(blocks):
            btype = block.get("type", "")
            if btype != "sheet":
                errors.append(IRValidationError(
                    path=f"blocks[{idx}].type",
                    code="spreadsheet_needs_sheet",
                    message="Top-level blocks in spreadsheet must be sheets",
                    expected="sheet",
                    actual=btype,
                ))
            children = block.get("children", [])
            if isinstance(children, list):
                for ci, child in enumerate(children):
                    ctype = child.get("type", "") if isinstance(child, dict) else ""
                    if allowed_in_sheet and ctype not in allowed_in_sheet:
                        errors.append(IRValidationError(
                            path=f"blocks[{idx}].children[{ci}].type",
                            code="unsupported_block_in_sheet",
                            message=f"Block type '{ctype}' not allowed inside sheet",
                            expected=" | ".join(sorted(allowed_in_sheet)),
                            actual=ctype,
                        ))
                    # Validate table inside sheet
                    if ctype == "table":
                        _validate_table(child, f"blocks[{idx}].children[{ci}]", errors)
                    # Validate range inside sheet
                    if ctype == "range":
                        _validate_range(child, f"blocks[{idx}].children[{ci}]", errors)
                    # Validate cell_patch inside sheet
                    if ctype == "cell_patch":
                        _validate_cell_patch(child, f"blocks[{idx}].children[{ci}]", errors)

    # Validate all tables in document/presentation/text/mixed blocks
    if content_type in ("document", "presentation", "text", "mixed"):
        _validate_tables_in_blocks(blocks, errors)

    # Mixed: resource_ref must resolve
    if content_type == "mixed":
        resource_ids = set()
        if isinstance(resources, list):
            for r in resources:
                rid = r.get("id")
                if rid is not None:
                    resource_ids.add(str(rid))
        _validate_resource_refs(blocks, resource_ids, errors)

    # Text: linearizable check (no complex nesting)
    if content_type == "text":
        allowed = profile.get("allowed_top_blocks", set())
        for idx, block in enumerate(blocks):
            btype = block.get("type", "")
            if btype not in allowed:
                expected_list = " | ".join(sorted(allowed))
                errors.append(IRValidationError(
                    path=f"blocks[{idx}].type",
                    code="text_block_not_allowed",
                    message=f"Block type '{btype}' not allowed in text content",
                    expected=expected_list,
                    actual=btype,
                ))


def _validate_resource_refs(
    blocks: list[dict], resource_ids: set[str],
    errors: list[IRValidationError], path_prefix: str = "blocks",
) -> None:
    for idx, block in enumerate(blocks):
        path = f"{path_prefix}[{idx}]"
        ref = block.get("resource_ref")
        if ref is not None and str(ref) not in resource_ids:
            errors.append(IRValidationError(
                path=f"{path}.resource_ref",
                code="unresolved_resource_ref",
                message=f"resource_ref '{ref}' does not match any resource id",
                actual=str(ref),
            ))
        children = block.get("children", [])
        if isinstance(children, list):
            _validate_resource_refs(children, resource_ids, errors, f"{path}.children")


def _validate_table(
    block: dict, path: str, errors: list[IRValidationError],
) -> None:
    """Validate table block data structure."""
    data = block.get("data", {})
    if not isinstance(data, dict):
        return
    headers = data.get("headers")
    rows = data.get("rows")
    if headers is not None and not isinstance(headers, list):
        errors.append(IRValidationError(
            path=f"{path}.data.headers",
            code="invalid_type",
            message="table.data.headers must be an array",
            expected="array",
            actual=type(headers).__name__,
        ))
    if rows is not None:
        if not isinstance(rows, list):
            errors.append(IRValidationError(
                path=f"{path}.data.rows",
                code="invalid_type",
                message="table.data.rows must be an array",
                expected="array",
                actual=type(rows).__name__,
            ))
        elif isinstance(rows, list) and isinstance(headers, list):
            for ri, row in enumerate(rows):
                if not isinstance(row, list):
                    errors.append(IRValidationError(
                        path=f"{path}.data.rows[{ri}]",
                        code="invalid_row_type",
                        message=f"Row {ri} must be an array",
                        expected="array",
                        actual=type(row).__name__,
                    ))
                elif len(row) != len(headers):
                    errors.append(IRValidationError(
                        path=f"{path}.data.rows[{ri}]",
                        code="row_length_mismatch",
                        message=f"Row {ri} length {len(row)} does not match headers length {len(headers)}",
                        expected=str(len(headers)),
                        actual=str(len(row)),
                    ))


def _validate_range(
    block: dict, path: str, errors: list[IRValidationError],
) -> None:
    """Validate range block - start_cell/end_cell must be valid Excel addresses."""
    data = block.get("data", {}) or {}
    start_cell = data.get("start_cell", "")
    if start_cell and not _is_valid_excel_addr(str(start_cell)):
        errors.append(IRValidationError(
            path=f"{path}.data.start_cell",
            code="invalid_excel_address",
            message=f"Invalid Excel address: {start_cell}",
            expected="valid Excel address like A1",
            actual=str(start_cell),
        ))
    end_cell = data.get("end_cell", "")
    if end_cell and not _is_valid_excel_addr(str(end_cell)):
        errors.append(IRValidationError(
            path=f"{path}.data.end_cell",
            code="invalid_excel_address",
            message=f"Invalid Excel address: {end_cell}",
            expected="valid Excel address like B10",
            actual=str(end_cell),
        ))


def _validate_cell_patch(
    block: dict, path: str, errors: list[IRValidationError],
) -> None:
    """Validate cell_patch block - address must be valid Excel address."""
    data = block.get("data", {}) or {}
    address = data.get("address", "")
    if address and not _is_valid_excel_addr(str(address)):
        errors.append(IRValidationError(
            path=f"{path}.data.address",
            code="invalid_excel_address",
            message=f"Invalid Excel address: {address}",
            expected="valid Excel address like A1",
            actual=str(address),
        ))


def _is_valid_excel_addr(addr: str) -> bool:
    """Check if string is a valid Excel cell address (e.g. A1, Z100, AA5)."""
    import re
    return bool(re.match(r'^[A-Za-z]{1,3}[1-9]\d*$', addr))


def _validate_tables_in_blocks(
    blocks: list[dict], errors: list[IRValidationError],
    path_prefix: str = "blocks",
) -> None:
    """Recursively validate all table blocks in a block tree."""
    for idx, block in enumerate(blocks):
        path = f"{path_prefix}[{idx}]"
        if isinstance(block, dict):
            if block.get("type") == "table":
                _validate_table(block, path, errors)
            children = block.get("children", [])
            if isinstance(children, list):
                _validate_tables_in_blocks(children, errors, f"{path}.children")


def validate_ir_sync(content_ir: dict[str, Any]) -> ValidationResult:
    """Synchronous wrapper for validate_ir (for non-async callers)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, validate_ir(content_ir))
            return future.result()
    return asyncio.run(validate_ir(content_ir))
