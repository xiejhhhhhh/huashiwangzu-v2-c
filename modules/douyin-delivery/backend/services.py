"""Service layer for douyin-delivery module."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import ValidationError
from app.database import AsyncSessionLocal
from app.gateway.service import chat as gateway_chat
from app.services.prompt_helpers import load_prompt_with_fallback
from sqlalchemy import select

from .models import DouyinAdCopy, DouyinCampaign, DouyinProduct, DouyinPrompt, DouyinScript

logger = logging.getLogger("v2.douyin_delivery").getChild("services")

MODULE_KEY = "douyin-delivery"
WRITING_PROFILE = "deepseek-v4-flash"

CHANNEL_LABELS = {
    "local_push": "本地推",
    "ocean_engine": "巨量引擎",
    "qianchuan": "千川",
}
VALID_CHANNELS = set(CHANNEL_LABELS)
VALID_SCRIPT_STATUSES = {"draft", "ready", "published", "archived"}
VALID_AD_COPY_STATUSES = {"draft", "ready", "published", "archived"}
VALID_CAMPAIGN_STATUSES = {"planning", "running", "paused", "ended"}
VALID_AD_TYPES = {"feed", "search", "brand"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_choice(field: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValidationError(f"Invalid {field}: {value}. Allowed: {allowed_text}")
    return value


def _require_text(field: str, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field} is required")
    return text


def _validate_optional_channel(channel: str | None) -> str:
    value = channel or ""
    if value:
        _validate_choice("channel", value, VALID_CHANNELS)
    return value


def _mark_deleted(row: Any) -> None:
    row.deleted = True
    row.updated_at = _now()


# ── Prompt helpers ──────────────────────────────────────────────

async def get_prompt(db, key: str, owner_id: int = 0) -> str | None:
    r = await db.execute(
        select(DouyinPrompt).where(
            DouyinPrompt.key == key,
            DouyinPrompt.owner_id.in_([0, owner_id]),
            DouyinPrompt.deleted.is_(False),
        ).order_by(DouyinPrompt.owner_id.desc()).limit(1)
    )
    prompt = r.scalar_one_or_none()
    return prompt.content if prompt else None


DEFAULT_FALLBACKS = {
    "persona_system": "你是一个专业的问题肌修护专家，代表俏小喵品牌。请用抖音口语化风格回答，短句、抓眼球、有亲和力。",
    "script_generation": "请为产品「{product}」生成一条抖音口播脚本，渠道：{channel}。包含开头钩子、痛点共鸣、卖点展开、信任背书、行动引导。",
    "ad_copy_generation": "请为产品「{product}」生成一条{channel_label}广告文案，类型：{ad_type}。包含标题、描述、行动号召、定向建议。",
    "ingredient_validation": "请校验以下内容的科学准确性：\n{content}",
}


async def _load_prompt_with_fallback(db, key: str, owner_id: int, **format_kwargs) -> str:
    return await load_prompt_with_fallback(
        db,
        key,
        owner_id,
        get_prompt,
        DEFAULT_FALLBACKS,
        logger=logger,
        **format_kwargs,
    )


# ── Script generation ───────────────────────────────────────────

async def generate_script(product: str, channel: str, owner_id: int) -> dict:
    product = _require_text("product", product)
    channel = _validate_choice("channel", channel or "local_push", VALID_CHANNELS)
    channel_label = CHANNEL_LABELS.get(channel, channel)
    async with AsyncSessionLocal() as db:
        system_prompt = await _load_prompt_with_fallback(db, "persona_system", owner_id)
        user_prompt = await _load_prompt_with_fallback(
            db, "script_generation", owner_id,
            product=product, channel=channel, channel_label=channel_label,
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = await gateway_chat(messages, profile_key=WRITING_PROFILE)
    return {"script": result.get("content", ""), "raw": result, "channel": channel, "channel_label": channel_label}


# ── Ad copy generation ──────────────────────────────────────────

async def generate_ad_copy(product: str, channel: str, ad_type: str, owner_id: int) -> dict:
    product = _require_text("product", product)
    channel = _validate_choice("channel", channel or "ocean_engine", VALID_CHANNELS)
    ad_type = _validate_choice("ad_type", ad_type or "feed", VALID_AD_TYPES)
    channel_label = CHANNEL_LABELS.get(channel, channel)
    async with AsyncSessionLocal() as db:
        system_prompt = await _load_prompt_with_fallback(db, "persona_system", owner_id)
        user_prompt = await _load_prompt_with_fallback(
            db, "ad_copy_generation", owner_id,
            product=product, channel=channel, channel_label=channel_label, ad_type=ad_type,
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = await gateway_chat(messages, profile_key=WRITING_PROFILE)
    return {"ad_copy": result.get("content", ""), "raw": result, "channel": channel, "channel_label": channel_label, "ad_type": ad_type}


# ── Content validation via knowledge base ───────────────────────

async def validate_content(content: str, owner_id: int) -> dict:
    from app.services.module_registry import call_capability

    content = _require_text("content", content)
    knowledge_error: str | None = None
    try:
        kb_result = await call_capability(
            "knowledge", "search",
            {"query": content, "top_k": 5},
            caller=f"user:{owner_id}",
            caller_role="viewer",
        )
        kb_results = kb_result.get("results", [])
        evidence_meta = kb_result.get("evidence_meta", {})
        has_knowledge = bool(kb_results)
    except Exception as exc:
        logger.warning("Knowledge search failed: %s", exc)
        kb_results = []
        evidence_meta = {}
        has_knowledge = False
        knowledge_error = str(exc)

    async with AsyncSessionLocal() as db:
        validation_prompt = await _load_prompt_with_fallback(db, "ingredient_validation", owner_id, content=content)
        persona = await _load_prompt_with_fallback(db, "persona_system", owner_id)

    messages = [
        {"role": "system", "content": persona + "\n\n你现在要做成分科学审核。"},
        {"role": "user", "content": validation_prompt},
    ]
    ai_review = await gateway_chat(messages, profile_key=WRITING_PROFILE)

    return {
        "has_knowledge_base_results": has_knowledge,
        "knowledge_results": kb_results,
        "evidence_meta": evidence_meta,
        "knowledge_error": knowledge_error,
        "ai_validation": ai_review.get("content", ""),
    }


# ── Campaign ROI analysis ───────────────────────────────────────

async def analyze_campaign(campaign_id: int, owner_id: int) -> dict | None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinCampaign).where(
                DouyinCampaign.id == campaign_id,
                DouyinCampaign.owner_id == owner_id,
                DouyinCampaign.deleted.is_(False),
            )
        )
        campaign = r.scalar_one_or_none()
        if not campaign:
            return None

    async with AsyncSessionLocal() as db:
        system_prompt = await _load_prompt_with_fallback(db, "persona_system", owner_id)

    metrics = campaign.performance_metrics or {}
    analysis_prompt = (
        f"请分析以下抖音投放计划的数据，给出优化建议：\n\n"
        f"计划名称：{campaign.name}\n"
        f"渠道：{CHANNEL_LABELS.get(campaign.channel, campaign.channel)}\n"
        f"预算：{campaign.budget}元（{campaign.budget_type}）\n"
        f"数据：{json.dumps(metrics, ensure_ascii=False)}\n\n"
        f"请给出：\n"
        f"1. 核心结论\n"
        f"2. 优化建议（3-5条）\n"
        f"3. 下一步行动计划"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": analysis_prompt},
    ]
    result = await gateway_chat(messages, profile_key=WRITING_PROFILE)

    return {
        "campaign": _campaign_to_dict(campaign),
        "analysis": result.get("content", ""),
        "raw": result,
    }


# ── Product CRUD ────────────────────────────────────────────────

async def list_products(owner_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinProduct).where(
                DouyinProduct.owner_id == owner_id,
                DouyinProduct.deleted.is_(False),
            ).order_by(DouyinProduct.updated_at.desc())
        )
        return [_product_to_dict(p) for p in r.scalars().all()]


async def create_product(data: dict, owner_id: int) -> dict:
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValidationError("Product name is required")
    async with AsyncSessionLocal() as db:
        product = DouyinProduct(
            owner_id=owner_id,
            name=name,
            category=data.get("category", ""),
            selling_points=data.get("selling_points"),
            ingredients=data.get("ingredients"),
            target_audience=data.get("target_audience", ""),
            brand=data.get("brand", "俏小喵"),
            notes=data.get("notes", ""),
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return _product_to_dict(product)


async def update_product(product_id: int, data: dict, owner_id: int) -> dict | None:
    if "name" in data and not str(data.get("name", "")).strip():
        raise ValidationError("Product name is required")
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinProduct).where(
                DouyinProduct.id == product_id,
                DouyinProduct.owner_id == owner_id,
                DouyinProduct.deleted.is_(False),
            )
        )
        product = r.scalar_one_or_none()
        if not product:
            return None
        for field in ("name", "category", "selling_points", "ingredients", "target_audience", "brand", "notes"):
            if field in data:
                setattr(product, field, data[field])
        await db.commit()
        await db.refresh(product)
        return _product_to_dict(product)


async def delete_product(product_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinProduct).where(
                DouyinProduct.id == product_id,
                DouyinProduct.owner_id == owner_id,
                DouyinProduct.deleted.is_(False),
            )
        )
        product = r.scalar_one_or_none()
        if not product:
            return False
        _mark_deleted(product)
        await db.commit()
        return True


# ── Script CRUD ─────────────────────────────────────────────────

async def list_scripts(owner_id: int, channel: str | None = None) -> list[dict]:
    async with AsyncSessionLocal() as db:
        query = select(DouyinScript).where(
            DouyinScript.owner_id == owner_id,
            DouyinScript.deleted.is_(False),
        )
        if channel:
            query = query.where(DouyinScript.channel == channel)
        query = query.order_by(DouyinScript.updated_at.desc())
        r = await db.execute(query)
        return [_script_to_dict(s) for s in r.scalars().all()]


async def save_script(data: dict, owner_id: int) -> dict:
    channel = _validate_choice("channel", data.get("channel", "local_push"), VALID_CHANNELS)
    status = _validate_choice("status", data.get("status", "draft"), VALID_SCRIPT_STATUSES)
    async with AsyncSessionLocal() as db:
        script = DouyinScript(
            owner_id=owner_id,
            title=data.get("title", ""),
            product_id=data.get("product_id"),
            product_name=data.get("product_name", ""),
            channel=channel,
            hook=data.get("hook", ""),
            pain_point=data.get("pain_point", ""),
            selling_point=data.get("selling_point", ""),
            social_proof=data.get("social_proof", ""),
            call_to_action=data.get("call_to_action", ""),
            full_script=data.get("full_script", ""),
            style_notes=data.get("style_notes", ""),
            hashtags=data.get("hashtags"),
            suggested_titles=data.get("suggested_titles"),
            status=status,
        )
        db.add(script)
        await db.commit()
        await db.refresh(script)
        return _script_to_dict(script)


async def get_script(script_id: int, owner_id: int) -> dict | None:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinScript).where(
                DouyinScript.id == script_id,
                DouyinScript.owner_id == owner_id,
                DouyinScript.deleted.is_(False),
            )
        )
        s = r.scalar_one_or_none()
        return _script_to_dict(s) if s else None


async def update_script(script_id: int, data: dict, owner_id: int) -> dict | None:
    if "channel" in data:
        data["channel"] = _validate_choice("channel", data["channel"], VALID_CHANNELS)
    if "status" in data:
        data["status"] = _validate_choice("status", data["status"], VALID_SCRIPT_STATUSES)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinScript).where(
                DouyinScript.id == script_id,
                DouyinScript.owner_id == owner_id,
                DouyinScript.deleted.is_(False),
            )
        )
        script = r.scalar_one_or_none()
        if not script:
            return None
        for field in ("title", "product_id", "product_name", "channel", "hook", "pain_point",
                      "selling_point", "social_proof", "call_to_action", "full_script",
                      "style_notes", "hashtags", "suggested_titles", "status"):
            if field in data:
                setattr(script, field, data[field])
        script.version += 1
        script.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(script)
        return _script_to_dict(script)


async def delete_script(script_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinScript).where(
                DouyinScript.id == script_id,
                DouyinScript.owner_id == owner_id,
                DouyinScript.deleted.is_(False),
            )
        )
        script = r.scalar_one_or_none()
        if not script:
            return False
        _mark_deleted(script)
        await db.commit()
        return True


# ── Ad Copy CRUD ────────────────────────────────────────────────

async def list_ad_copies(owner_id: int, channel: str | None = None) -> list[dict]:
    async with AsyncSessionLocal() as db:
        query = select(DouyinAdCopy).where(
            DouyinAdCopy.owner_id == owner_id,
            DouyinAdCopy.deleted.is_(False),
        )
        if channel:
            query = query.where(DouyinAdCopy.channel == channel)
        query = query.order_by(DouyinAdCopy.updated_at.desc())
        r = await db.execute(query)
        return [_ad_copy_to_dict(c) for c in r.scalars().all()]


async def save_ad_copy(data: dict, owner_id: int) -> dict:
    channel = _validate_choice("channel", data.get("channel", "ocean_engine"), VALID_CHANNELS)
    ad_type = _validate_choice("ad_type", data.get("ad_type", "feed"), VALID_AD_TYPES)
    status = _validate_choice("status", data.get("status", "draft"), VALID_AD_COPY_STATUSES)
    async with AsyncSessionLocal() as db:
        copy = DouyinAdCopy(
            owner_id=owner_id,
            product_id=data.get("product_id"),
            product_name=data.get("product_name", ""),
            channel=channel,
            ad_type=ad_type,
            title=data.get("title", ""),
            headline=data.get("headline", ""),
            description=data.get("description", ""),
            call_to_action=data.get("call_to_action", "立即购买"),
            target_audience_desc=data.get("target_audience_desc", ""),
            landing_page_suggestion=data.get("landing_page_suggestion", ""),
            status=status,
        )
        db.add(copy)
        await db.commit()
        await db.refresh(copy)
        return _ad_copy_to_dict(copy)


async def update_ad_copy(copy_id: int, data: dict, owner_id: int) -> dict | None:
    if "channel" in data:
        data["channel"] = _validate_choice("channel", data["channel"], VALID_CHANNELS)
    if "ad_type" in data:
        data["ad_type"] = _validate_choice("ad_type", data["ad_type"], VALID_AD_TYPES)
    if "status" in data:
        data["status"] = _validate_choice("status", data["status"], VALID_AD_COPY_STATUSES)
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinAdCopy).where(
                DouyinAdCopy.id == copy_id,
                DouyinAdCopy.owner_id == owner_id,
                DouyinAdCopy.deleted.is_(False),
            )
        )
        copy = r.scalar_one_or_none()
        if not copy:
            return None
        for field in ("product_id", "product_name", "channel", "ad_type", "title",
                      "headline", "description", "call_to_action", "target_audience_desc",
                      "landing_page_suggestion", "status"):
            if field in data:
                setattr(copy, field, data[field])
        copy.version += 1
        copy.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(copy)
        return _ad_copy_to_dict(copy)


async def delete_ad_copy(copy_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinAdCopy).where(
                DouyinAdCopy.id == copy_id,
                DouyinAdCopy.owner_id == owner_id,
                DouyinAdCopy.deleted.is_(False),
            )
        )
        copy = r.scalar_one_or_none()
        if not copy:
            return False
        _mark_deleted(copy)
        await db.commit()
        return True


# ── Campaign CRUD ───────────────────────────────────────────────

async def list_campaigns(owner_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinCampaign).where(
                DouyinCampaign.owner_id == owner_id,
                DouyinCampaign.deleted.is_(False),
            ).order_by(DouyinCampaign.updated_at.desc())
        )
        return [_campaign_to_dict(c) for c in r.scalars().all()]


async def create_campaign(data: dict, owner_id: int) -> dict:
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValidationError("Campaign name is required")
    channel = _validate_choice("channel", data.get("channel", "local_push"), VALID_CHANNELS)
    status = _validate_choice("status", data.get("status", "planning"), VALID_CAMPAIGN_STATUSES)
    budget_type = _validate_choice("budget_type", data.get("budget_type", "daily"), {"daily", "total"})
    async with AsyncSessionLocal() as db:
        campaign = DouyinCampaign(
            owner_id=owner_id,
            name=name,
            channel=channel,
            status=status,
            budget=data.get("budget"),
            budget_type=budget_type,
            start_date=data.get("start_date", ""),
            end_date=data.get("end_date", ""),
            target_audience=data.get("target_audience"),
            product_ids=data.get("product_ids"),
            script_ids=data.get("script_ids"),
            ad_copy_ids=data.get("ad_copy_ids"),
            notes=data.get("notes", ""),
            performance_metrics=data.get("performance_metrics"),
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        return _campaign_to_dict(campaign)


async def update_campaign(campaign_id: int, data: dict, owner_id: int) -> dict | None:
    if "name" in data and not str(data.get("name", "")).strip():
        raise ValidationError("Campaign name is required")
    if "channel" in data:
        data["channel"] = _validate_choice("channel", data["channel"], VALID_CHANNELS)
    if "status" in data:
        data["status"] = _validate_choice("status", data["status"], VALID_CAMPAIGN_STATUSES)
    if "budget_type" in data:
        data["budget_type"] = _validate_choice("budget_type", data["budget_type"], {"daily", "total"})
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinCampaign).where(
                DouyinCampaign.id == campaign_id,
                DouyinCampaign.owner_id == owner_id,
                DouyinCampaign.deleted.is_(False),
            )
        )
        campaign = r.scalar_one_or_none()
        if not campaign:
            return None
        for field in ("name", "channel", "status", "budget", "budget_type", "start_date",
                      "end_date", "target_audience", "product_ids", "script_ids",
                      "ad_copy_ids", "notes", "performance_metrics"):
            if field in data:
                setattr(campaign, field, data[field])
        campaign.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(campaign)
        return _campaign_to_dict(campaign)


async def delete_campaign(campaign_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinCampaign).where(
                DouyinCampaign.id == campaign_id,
                DouyinCampaign.owner_id == owner_id,
                DouyinCampaign.deleted.is_(False),
            )
        )
        campaign = r.scalar_one_or_none()
        if not campaign:
            return False
        _mark_deleted(campaign)
        await db.commit()
        return True




# ── Prompt CRUD ─────────────────────────────────────────────────

async def list_prompts(owner_id: int, category: str | None = None, channel: str | None = None) -> list[dict]:
    async with AsyncSessionLocal() as db:
        query = select(DouyinPrompt).where(
            DouyinPrompt.owner_id.in_([0, owner_id]),
            DouyinPrompt.deleted.is_(False),
        )
        if category:
            query = query.where(DouyinPrompt.category == category)
        if channel:
            query = query.where(DouyinPrompt.channel.in_(["", channel]))
        query = query.order_by(DouyinPrompt.category, DouyinPrompt.key)
        r = await db.execute(query)
        items = r.scalars().all()
        seen = {}
        for p in items:
            seen[p.key] = p
        return [_prompt_to_dict(p) for p in seen.values()]


async def save_prompt(data: dict, owner_id: int) -> dict:
    key = str(data.get("key", "")).strip()
    content = str(data.get("content", "")).strip()
    if not key:
        raise ValidationError("Prompt key is required")
    if not content:
        raise ValidationError("Prompt content is required")
    _validate_optional_channel(data.get("channel", ""))
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinPrompt).where(
                DouyinPrompt.key == key,
                DouyinPrompt.owner_id == owner_id,
                DouyinPrompt.deleted.is_(False),
            )
        )
        existing = r.scalar_one_or_none()
        if existing:
            existing.content = content
            existing.name = data.get("name", existing.name)
            existing.description = data.get("description", existing.description)
            existing.category = data.get("category", existing.category)
            existing.channel = data.get("channel", existing.channel)
            existing.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing)
            return _prompt_to_dict(existing)
        else:
            prompt = DouyinPrompt(
                owner_id=owner_id,
                key=key,
                name=data.get("name", key),
                content=content,
                description=data.get("description", ""),
                category=data.get("category", "custom"),
                channel=data.get("channel", ""),
            )
            db.add(prompt)
            await db.commit()
            await db.refresh(prompt)
            return _prompt_to_dict(prompt)


async def delete_prompt(prompt_id: int, owner_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(DouyinPrompt).where(
                DouyinPrompt.id == prompt_id,
                DouyinPrompt.owner_id == owner_id,
                DouyinPrompt.deleted.is_(False),
            )
        )
        p = r.scalar_one_or_none()
        if not p:
            return False
        _mark_deleted(p)
        await db.commit()
        return True


# ── Helpers ─────────────────────────────────────────────────────

def _product_to_dict(p: DouyinProduct) -> dict:
    return {
        "id": p.id,
        "owner_id": p.owner_id,
        "name": p.name,
        "category": p.category,
        "selling_points": p.selling_points,
        "ingredients": p.ingredients,
        "target_audience": p.target_audience,
        "brand": p.brand,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _script_to_dict(s: DouyinScript) -> dict:
    return {
        "id": s.id,
        "owner_id": s.owner_id,
        "title": s.title,
        "product_id": s.product_id,
        "product_name": s.product_name,
        "channel": s.channel,
        "hook": s.hook,
        "pain_point": s.pain_point,
        "selling_point": s.selling_point,
        "social_proof": s.social_proof,
        "call_to_action": s.call_to_action,
        "full_script": s.full_script,
        "style_notes": s.style_notes,
        "hashtags": s.hashtags,
        "suggested_titles": s.suggested_titles,
        "status": s.status,
        "version": s.version,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _ad_copy_to_dict(c: DouyinAdCopy) -> dict:
    return {
        "id": c.id,
        "owner_id": c.owner_id,
        "product_id": c.product_id,
        "product_name": c.product_name,
        "channel": c.channel,
        "ad_type": c.ad_type,
        "title": c.title,
        "headline": c.headline,
        "description": c.description,
        "call_to_action": c.call_to_action,
        "target_audience_desc": c.target_audience_desc,
        "landing_page_suggestion": c.landing_page_suggestion,
        "status": c.status,
        "version": c.version,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _campaign_to_dict(c: DouyinCampaign) -> dict:
    return {
        "id": c.id,
        "owner_id": c.owner_id,
        "name": c.name,
        "channel": c.channel,
        "status": c.status,
        "budget": c.budget,
        "budget_type": c.budget_type,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "target_audience": c.target_audience,
        "product_ids": c.product_ids,
        "script_ids": c.script_ids,
        "ad_copy_ids": c.ad_copy_ids,
        "notes": c.notes,
        "performance_metrics": c.performance_metrics,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }



def _prompt_to_dict(p: DouyinPrompt) -> dict:
    return {
        "id": p.id,
        "owner_id": p.owner_id,
        "key": p.key,
        "name": p.name,
        "content": p.content,
        "description": p.description,
        "category": p.category,
        "channel": p.channel,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
