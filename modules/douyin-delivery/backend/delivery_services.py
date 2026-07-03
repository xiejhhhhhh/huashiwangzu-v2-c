"""Delivery account, material, task, and cleanup services."""

from datetime import datetime, timezone

from app.core.exceptions import ValidationError
from app.database import AsyncSessionLocal
from sqlalchemy import Text, cast, delete, or_, select

from .models import (
    DouyinAccount,
    DouyinAdCopy,
    DouyinCampaign,
    DouyinDeliveryTask,
    DouyinMaterial,
    DouyinProduct,
    DouyinPrompt,
    DouyinScript,
)

VALID_CHANNELS = {"local_push", "ocean_engine", "qianchuan"}
VALID_ACCOUNT_STATUSES = {"active", "paused", "disabled"}
VALID_MATERIAL_TYPES = {"video", "image", "text", "landing_page"}
VALID_MATERIAL_STATUSES = {"draft", "ready", "published", "archived"}
VALID_DELIVERY_TASK_TYPES = {"publish_script", "publish_ad_copy", "sync_metrics", "review_content"}
VALID_DELIVERY_TARGET_TYPES = {"script", "ad_copy", "campaign", "material"}
VALID_DELIVERY_TASK_STATUSES = {"pending", "running", "succeeded", "failed", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_choice(field: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValidationError(f"Invalid {field}: {value}. Allowed: {allowed_text}")
    return value


def _validate_optional_channel(channel: str | None) -> str:
    value = channel or ""
    if value:
        _validate_choice("channel", value, VALID_CHANNELS)
    return value


def _mark_deleted(row: object) -> None:
    setattr(row, "deleted", True)
    setattr(row, "updated_at", _now())


def _require_marker(marker: str) -> str:
    value = marker.strip()
    if len(value) < 6:
        raise ValidationError("cleanup marker must be at least 6 characters")
    return value


def _has_failure_signal(value: object) -> bool:
    if isinstance(value, dict):
        if value.get("success") is False:
            return True
        status = str(value.get("status") or value.get("state") or "").strip().lower()
        if status in {"failed", "failure", "error", "rejected"}:
            return True
        for key in ("error", "error_message", "failure_reason"):
            if str(value.get(key) or "").strip():
                return True
        return any(_has_failure_signal(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_failure_signal(item) for item in value)
    return False


def _validate_task_result_semantics(status: str, error_message: str, result_payload: dict | None) -> None:
    has_error_message = bool(error_message.strip())
    if status == "failed":
        if not has_error_message:
            raise ValidationError("Failed delivery task requires error_message")
        return
    if has_error_message:
        raise ValidationError("error_message is only allowed when delivery task status is failed")
    if status == "succeeded" and _has_failure_signal(result_payload):
        raise ValidationError("Succeeded delivery task result_payload must not contain failure semantics")


async def list_accounts(owner_id: int, channel: str | None = None) -> list[dict]:
    channel = _validate_optional_channel(channel)
    async with AsyncSessionLocal() as db:
        query = select(DouyinAccount).where(
            DouyinAccount.owner_id == owner_id,
            DouyinAccount.deleted.is_(False),
        )
        if channel:
            query = query.where(DouyinAccount.channel == channel)
        query = query.order_by(DouyinAccount.updated_at.desc())
        r = await db.execute(query)
        return [_account_to_dict(a) for a in r.scalars().all()]


async def create_account(data: dict, owner_id: int) -> dict:
    account_name = str(data.get("account_name", "")).strip()
    if not account_name:
        raise ValidationError("Account name is required")
    channel = _validate_choice("channel", data.get("channel", "local_push"), VALID_CHANNELS)
    status = _validate_choice("status", data.get("status", "active"), VALID_ACCOUNT_STATUSES)
    async with AsyncSessionLocal() as db:
        account = DouyinAccount(
            owner_id=owner_id,
            channel=channel,
            account_name=account_name,
            external_account_id=data.get("external_account_id", ""),
            status=status,
            notes=data.get("notes", ""),
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
        return _account_to_dict(account)


async def update_account(account_id: int, data: dict, owner_id: int) -> dict | None:
    if "account_name" in data and not str(data.get("account_name", "")).strip():
        raise ValidationError("Account name is required")
    if "channel" in data:
        data["channel"] = _validate_choice("channel", data["channel"], VALID_CHANNELS)
    if "status" in data:
        data["status"] = _validate_choice("status", data["status"], VALID_ACCOUNT_STATUSES)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinAccount).where(
                DouyinAccount.id == account_id,
                DouyinAccount.owner_id == owner_id,
                DouyinAccount.deleted.is_(False),
            )
        )
        account = r.scalar_one_or_none()
        if not account:
            return None
        for field in ("channel", "account_name", "external_account_id", "status", "notes"):
            if field in data:
                setattr(account, field, data[field])
        account.updated_at = _now()
        await db.commit()
        await db.refresh(account)
        return _account_to_dict(account)


async def delete_account(account_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinAccount).where(
                DouyinAccount.id == account_id,
                DouyinAccount.owner_id == owner_id,
                DouyinAccount.deleted.is_(False),
            )
        )
        account = r.scalar_one_or_none()
        if not account:
            return False
        _mark_deleted(account)
        await db.commit()
        return True


async def list_materials(owner_id: int, material_type: str | None = None, status: str | None = None) -> list[dict]:
    if material_type:
        _validate_choice("material_type", material_type, VALID_MATERIAL_TYPES)
    if status:
        _validate_choice("status", status, VALID_MATERIAL_STATUSES)
    async with AsyncSessionLocal() as db:
        query = select(DouyinMaterial).where(
            DouyinMaterial.owner_id == owner_id,
            DouyinMaterial.deleted.is_(False),
        )
        if material_type:
            query = query.where(DouyinMaterial.material_type == material_type)
        if status:
            query = query.where(DouyinMaterial.status == status)
        query = query.order_by(DouyinMaterial.updated_at.desc())
        r = await db.execute(query)
        return [_material_to_dict(m) for m in r.scalars().all()]


async def create_material(data: dict, owner_id: int) -> dict:
    title = str(data.get("title", "")).strip()
    if not title:
        raise ValidationError("Material title is required")
    material_type = _validate_choice("material_type", data.get("material_type", "video"), VALID_MATERIAL_TYPES)
    channel = _validate_optional_channel(data.get("channel", ""))
    status = _validate_choice("status", data.get("status", "draft"), VALID_MATERIAL_STATUSES)
    async with AsyncSessionLocal() as db:
        material = DouyinMaterial(
            owner_id=owner_id,
            title=title,
            material_type=material_type,
            channel=channel,
            source_file_id=data.get("source_file_id"),
            content_url=data.get("content_url", ""),
            content_text=data.get("content_text", ""),
            status=status,
            notes=data.get("notes", ""),
            metadata_json=data.get("metadata_json"),
        )
        db.add(material)
        await db.commit()
        await db.refresh(material)
        return _material_to_dict(material)


async def update_material(material_id: int, data: dict, owner_id: int) -> dict | None:
    if "title" in data and not str(data.get("title", "")).strip():
        raise ValidationError("Material title is required")
    if "material_type" in data:
        data["material_type"] = _validate_choice("material_type", data["material_type"], VALID_MATERIAL_TYPES)
    if "channel" in data:
        data["channel"] = _validate_optional_channel(data["channel"])
    if "status" in data:
        data["status"] = _validate_choice("status", data["status"], VALID_MATERIAL_STATUSES)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinMaterial).where(
                DouyinMaterial.id == material_id,
                DouyinMaterial.owner_id == owner_id,
                DouyinMaterial.deleted.is_(False),
            )
        )
        material = r.scalar_one_or_none()
        if not material:
            return None
        for field in (
            "title",
            "material_type",
            "channel",
            "source_file_id",
            "content_url",
            "content_text",
            "status",
            "notes",
            "metadata_json",
        ):
            if field in data:
                setattr(material, field, data[field])
        material.updated_at = _now()
        await db.commit()
        await db.refresh(material)
        return _material_to_dict(material)


async def delete_material(material_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinMaterial).where(
                DouyinMaterial.id == material_id,
                DouyinMaterial.owner_id == owner_id,
                DouyinMaterial.deleted.is_(False),
            )
        )
        material = r.scalar_one_or_none()
        if not material:
            return False
        _mark_deleted(material)
        await db.commit()
        return True


async def list_delivery_tasks(owner_id: int, status: str | None = None, task_type: str | None = None) -> list[dict]:
    if status:
        _validate_choice("status", status, VALID_DELIVERY_TASK_STATUSES)
    if task_type:
        _validate_choice("task_type", task_type, VALID_DELIVERY_TASK_TYPES)
    async with AsyncSessionLocal() as db:
        query = select(DouyinDeliveryTask).where(
            DouyinDeliveryTask.owner_id == owner_id,
            DouyinDeliveryTask.deleted.is_(False),
        )
        if status:
            query = query.where(DouyinDeliveryTask.status == status)
        if task_type:
            query = query.where(DouyinDeliveryTask.task_type == task_type)
        query = query.order_by(DouyinDeliveryTask.updated_at.desc())
        r = await db.execute(query)
        return [_delivery_task_to_dict(t) for t in r.scalars().all()]


async def create_delivery_task(data: dict, owner_id: int) -> dict:
    task_type = _validate_choice("task_type", data.get("task_type", "publish_script"), VALID_DELIVERY_TASK_TYPES)
    target_type = _validate_choice("target_type", data.get("target_type", "campaign"), VALID_DELIVERY_TARGET_TYPES)
    status = _validate_choice("status", data.get("status", "pending"), VALID_DELIVERY_TASK_STATUSES)
    error_message = str(data.get("error_message", "") or "")
    result_payload = data.get("result_payload")
    _validate_task_result_semantics(status, error_message, result_payload)
    now = _now()
    async with AsyncSessionLocal() as db:
        task = DouyinDeliveryTask(
            owner_id=owner_id,
            task_type=task_type,
            target_type=target_type,
            target_id=data.get("target_id"),
            status=status,
            priority=int(data.get("priority", 5)),
            payload=data.get("payload"),
            result_payload=result_payload,
            error_message=error_message,
            started_at=now if status == "running" else data.get("started_at"),
            finished_at=now if status in {"succeeded", "failed", "cancelled"} else data.get("finished_at"),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return _delivery_task_to_dict(task)


async def update_delivery_task(task_id: int, data: dict, owner_id: int) -> dict | None:
    for field, allowed in (
        ("task_type", VALID_DELIVERY_TASK_TYPES),
        ("target_type", VALID_DELIVERY_TARGET_TYPES),
        ("status", VALID_DELIVERY_TASK_STATUSES),
    ):
        if field in data:
            data[field] = _validate_choice(field, data[field], allowed)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinDeliveryTask).where(
                DouyinDeliveryTask.id == task_id,
                DouyinDeliveryTask.owner_id == owner_id,
                DouyinDeliveryTask.deleted.is_(False),
            )
        )
        task = r.scalar_one_or_none()
        if not task:
            return None
        status = data.get("status", task.status)
        error_message = str(data.get("error_message", task.error_message or "") or "")
        result_payload = data.get("result_payload", task.result_payload)
        _validate_task_result_semantics(status, error_message, result_payload)
        for field in (
            "task_type",
            "target_type",
            "target_id",
            "status",
            "priority",
            "payload",
            "result_payload",
            "error_message",
            "started_at",
            "finished_at",
        ):
            if field in data:
                setattr(task, field, data[field])
        _apply_task_status_timestamps(task)
        task.updated_at = _now()
        await db.commit()
        await db.refresh(task)
        return _delivery_task_to_dict(task)


async def mark_delivery_task_status(
    task_id: int,
    owner_id: int,
    status: str,
    error_message: str = "",
    result_payload: dict | None = None,
) -> dict | None:
    status = _validate_choice("status", status, VALID_DELIVERY_TASK_STATUSES)
    if status == "failed" and not error_message.strip():
        raise ValidationError("Failed delivery task requires error_message")
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinDeliveryTask).where(
                DouyinDeliveryTask.id == task_id,
                DouyinDeliveryTask.owner_id == owner_id,
                DouyinDeliveryTask.deleted.is_(False),
            )
        )
        task = r.scalar_one_or_none()
        if not task:
            return None
        _validate_task_result_semantics(status, error_message, result_payload)
        task.status = status
        task.error_message = error_message if status == "failed" else ""
        if result_payload is not None:
            task.result_payload = result_payload
        _apply_task_status_timestamps(task)
        task.updated_at = _now()
        await db.commit()
        await db.refresh(task)
        return _delivery_task_to_dict(task)


async def delete_delivery_task(task_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinDeliveryTask).where(
                DouyinDeliveryTask.id == task_id,
                DouyinDeliveryTask.owner_id == owner_id,
                DouyinDeliveryTask.deleted.is_(False),
            )
        )
        task = r.scalar_one_or_none()
        if not task:
            return False
        _mark_deleted(task)
        await db.commit()
        return True


def _apply_task_status_timestamps(task: DouyinDeliveryTask) -> None:
    now = _now()
    if task.status == "running" and task.started_at is None:
        task.started_at = now
    if task.status in {"succeeded", "failed", "cancelled"} and task.finished_at is None:
        task.finished_at = now


async def cleanup_marked_data(owner_id: int, marker: str) -> dict:
    marker = _require_marker(marker)
    pattern = f"%{marker}%"
    async with AsyncSessionLocal() as db:
        targets = (
            (DouyinProduct, (DouyinProduct.name, DouyinProduct.notes)),
            (DouyinScript, (DouyinScript.title, DouyinScript.product_name, DouyinScript.full_script)),
            (DouyinAdCopy, (DouyinAdCopy.title, DouyinAdCopy.product_name, DouyinAdCopy.description)),
            (DouyinCampaign, (DouyinCampaign.name, DouyinCampaign.notes)),
            (DouyinAccount, (DouyinAccount.account_name, DouyinAccount.external_account_id, DouyinAccount.notes)),
            (DouyinMaterial, (DouyinMaterial.title, DouyinMaterial.content_url, DouyinMaterial.content_text, DouyinMaterial.notes)),
            (DouyinPrompt, (DouyinPrompt.key, DouyinPrompt.name, DouyinPrompt.content)),
        )
        counts: dict[str, int] = {}
        total = 0
        for model, columns in targets:
            condition = or_(*(column.ilike(pattern) for column in columns))
            result = await db.execute(delete(model).where(model.owner_id == owner_id, condition))
            count = result.rowcount or 0
            counts[model.__tablename__] = count
            total += count

        task_result = await db.execute(
            delete(DouyinDeliveryTask).where(
                DouyinDeliveryTask.owner_id == owner_id,
                or_(
                    DouyinDeliveryTask.task_type.ilike(pattern),
                    DouyinDeliveryTask.target_type.ilike(pattern),
                    DouyinDeliveryTask.error_message.ilike(pattern),
                    cast(DouyinDeliveryTask.payload, Text).ilike(pattern),
                    cast(DouyinDeliveryTask.result_payload, Text).ilike(pattern),
                ),
            )
        )
        task_count = task_result.rowcount or 0
        counts[DouyinDeliveryTask.__tablename__] = task_count
        total += task_count

        await db.commit()
        return {"marker": marker, "deleted": counts, "total_deleted": total}


def _account_to_dict(a: DouyinAccount) -> dict:
    return {
        "id": a.id,
        "owner_id": a.owner_id,
        "channel": a.channel,
        "account_name": a.account_name,
        "external_account_id": a.external_account_id,
        "status": a.status,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _material_to_dict(m: DouyinMaterial) -> dict:
    return {
        "id": m.id,
        "owner_id": m.owner_id,
        "title": m.title,
        "material_type": m.material_type,
        "channel": m.channel,
        "source_file_id": m.source_file_id,
        "content_url": m.content_url,
        "content_text": m.content_text,
        "status": m.status,
        "notes": m.notes,
        "metadata_json": m.metadata_json,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _delivery_task_to_dict(t: DouyinDeliveryTask) -> dict:
    return {
        "id": t.id,
        "owner_id": t.owner_id,
        "task_type": t.task_type,
        "target_type": t.target_type,
        "target_id": t.target_id,
        "status": t.status,
        "priority": t.priority,
        "payload": t.payload,
        "result_payload": t.result_payload,
        "error_message": t.error_message,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
