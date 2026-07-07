"""Perceptual image fingerprinting and conservative similarity grouping."""
from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass

from PIL import Image
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbImageAsset, KbImageSimilarityGroup, KbImageSimilarPair, KbRawData

IMAGE_HASH_SCHEMA_VERSION = "image_hash_v1"
IMAGE_SIMILARITY_CALC_VERSION = "image_similarity_v1"

PHASH_HIGH_DISTANCE = 8
PHASH_SUSPECTED_DISTANCE = 16
DHASH_HIGH_DISTANCE = 6
DHASH_SUSPECTED_DISTANCE = 14
OCR_HIGH_SIMILARITY = 0.85


@dataclass(frozen=True)
class ImageFingerprints:
    width: int
    height: int
    file_md5: str
    ahash: str
    dhash: str
    phash: str


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = max(1, math.ceil(len(bits) / 4))
    return f"{value:0{width}x}"


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _image_values(image: Image.Image) -> list[int]:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def _dct_coefficient(pixels: list[list[int]], u: int, v: int, size: int) -> float:
    total = 0.0
    for y in range(size):
        for x in range(size):
            total += (
                pixels[y][x]
                * math.cos(((2 * x + 1) * u * math.pi) / (2 * size))
                * math.cos(((2 * y + 1) * v * math.pi) / (2 * size))
            )
    cu = 1 / math.sqrt(2) if u == 0 else 1
    cv = 1 / math.sqrt(2) if v == 0 else 1
    return 0.25 * cu * cv * total


def _ahash(image: Image.Image) -> str:
    grayscale = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    values = _image_values(grayscale)
    avg = sum(values) / len(values)
    return _bits_to_hex([value >= avg for value in values])


def _dhash(image: Image.Image) -> str:
    grayscale = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    values = _image_values(grayscale)
    bits: list[bool] = []
    for row in range(8):
        offset = row * 9
        for col in range(8):
            bits.append(values[offset + col] > values[offset + col + 1])
    return _bits_to_hex(bits)


def _phash(image: Image.Image) -> str:
    size = 32
    grayscale = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    flat_values = _image_values(grayscale)
    pixels = [flat_values[index:index + size] for index in range(0, len(flat_values), size)]
    low_freq = [
        _dct_coefficient(pixels, u, v, size)
        for v in range(8)
        for u in range(8)
    ]
    threshold = _median(low_freq[1:])
    return _bits_to_hex([value >= threshold for value in low_freq])


def compute_image_fingerprints(image_bytes: bytes) -> ImageFingerprints:
    """Compute stable local perceptual hashes without storing image bytes."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        width, height = image.size
        return ImageFingerprints(
            width=width,
            height=height,
            file_md5=hashlib.md5(image_bytes).hexdigest(),
            ahash=_ahash(image),
            dhash=_dhash(image),
            phash=_phash(image),
        )


def hamming_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count() + abs(len(left) - len(right)) * 4
    except ValueError:
        return None


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_ocr_text(text).encode("utf-8")).hexdigest()


def ocr_text_similarity(left: str, right: str) -> float | None:
    left_norm = normalize_ocr_text(left)
    right_norm = normalize_ocr_text(right)
    if not left_norm or not right_norm:
        return None
    left_units = set(left_norm) if len(left_norm) < 4 else {left_norm[i:i + 3] for i in range(len(left_norm) - 2)}
    right_units = set(right_norm) if len(right_norm) < 4 else {right_norm[i:i + 3] for i in range(len(right_norm) - 2)}
    if not left_units or not right_units:
        return None
    return len(left_units & right_units) / len(left_units | right_units)


def classify_similarity(
    *,
    hamming_phash: int | None,
    hamming_dhash: int | None,
    text_similarity: float | None,
) -> tuple[str, str]:
    phash_high = hamming_phash is not None and hamming_phash <= PHASH_HIGH_DISTANCE
    dhash_high = hamming_dhash is not None and hamming_dhash <= DHASH_HIGH_DISTANCE
    phash_suspected = hamming_phash is not None and hamming_phash <= PHASH_SUSPECTED_DISTANCE
    dhash_suspected = hamming_dhash is not None and hamming_dhash <= DHASH_SUSPECTED_DISTANCE
    ocr_high = text_similarity is not None and text_similarity >= OCR_HIGH_SIMILARITY

    if phash_high and dhash_high:
        reason = f"phash<={PHASH_HIGH_DISTANCE} and dhash<={DHASH_HIGH_DISTANCE}"
        if ocr_high:
            reason += " with high OCR similarity"
        return "high", reason
    if (phash_high or dhash_high) and ocr_high:
        return "high", "one perceptual hash is high and OCR text is highly similar"
    if phash_suspected and dhash_suspected:
        return "suspected", f"phash<={PHASH_SUSPECTED_DISTANCE} and dhash<={DHASH_SUSPECTED_DISTANCE}"
    if phash_suspected or dhash_suspected or ocr_high:
        return "suspected", "single weak similarity signal"
    return "different", "perceptual hashes and OCR text are not close enough"


async def _latest_raw_for_page(db: AsyncSession, document_id: int, page: int) -> tuple[int | None, str]:
    result = await db.execute(
        select(KbRawData)
        .where(
            KbRawData.document_id == document_id,
            KbRawData.page == page,
            KbRawData.source_type.in_(("vision", "ocr")),
        )
        .order_by(KbRawData.round.desc(), KbRawData.id.desc())
    )
    rows = result.scalars().all()
    raw_data_id = int(rows[0].id) if rows else None
    ocr_text = "\n".join(row.content or "" for row in rows if row.source_type == "ocr")
    return raw_data_id, ocr_text


async def _upsert_asset(
    db: AsyncSession,
    *,
    owner_id: int,
    document_id: int,
    file_id: int,
    page: int,
    image_bytes: bytes,
    asset_type: str,
    preprocess: dict | None = None,
) -> KbImageAsset:
    fingerprints = compute_image_fingerprints(image_bytes)
    raw_data_id, ocr_text = await _latest_raw_for_page(db, document_id, page)
    existing = await db.scalar(
        select(KbImageAsset)
        .where(
            KbImageAsset.owner_id == owner_id,
            KbImageAsset.document_id == document_id,
            KbImageAsset.page == page,
            KbImageAsset.hash_schema_version == IMAGE_HASH_SCHEMA_VERSION,
        )
        .limit(1)
    )
    asset = existing or KbImageAsset(
        owner_id=owner_id,
        document_id=document_id,
        file_id=file_id,
        page=page,
        hash_schema_version=IMAGE_HASH_SCHEMA_VERSION,
    )
    if existing is None:
        db.add(asset)
    asset.raw_data_id = raw_data_id
    asset.asset_type = asset_type
    asset.width = fingerprints.width
    asset.height = fingerprints.height
    asset.file_md5 = fingerprints.file_md5
    asset.ahash = fingerprints.ahash
    asset.dhash = fingerprints.dhash
    asset.phash = fingerprints.phash
    asset.ocr_text_hash = text_hash(ocr_text) if ocr_text else None
    asset.status = "active"
    asset.diagnostics_json = {
        "hash_schema_version": IMAGE_HASH_SCHEMA_VERSION,
        "image_bytes_md5": fingerprints.file_md5,
        "source_original_md5": (preprocess or {}).get("source_original_md5"),
        "source_prepared_md5": (preprocess or {}).get("source_prepared_md5") or fingerprints.file_md5,
        "vlm_image_preprocess": preprocess or {},
        "ocr_text_normalized": normalize_ocr_text(ocr_text)[:2000],
        "ocr_text_length": len(normalize_ocr_text(ocr_text)),
        "phase": "image_similarity_minimal",
        "vlm_reuse": False,
    }
    await db.flush()
    return asset


async def _upsert_pair(
    db: AsyncSession,
    *,
    owner_id: int,
    source_asset_id: int,
    target_asset_id: int,
    hamming_phash: int | None,
    hamming_dhash: int | None,
    text_similarity: float | None,
    similarity_level: str,
    decision_reason: str,
) -> KbImageSimilarPair:
    left_id, right_id = sorted((source_asset_id, target_asset_id))
    pair = await db.scalar(
        select(KbImageSimilarPair)
        .where(
            KbImageSimilarPair.source_asset_id == left_id,
            KbImageSimilarPair.target_asset_id == right_id,
            KbImageSimilarPair.calc_version == IMAGE_SIMILARITY_CALC_VERSION,
        )
        .limit(1)
    )
    if pair is None:
        pair = KbImageSimilarPair(
            owner_id=owner_id,
            source_asset_id=left_id,
            target_asset_id=right_id,
            calc_version=IMAGE_SIMILARITY_CALC_VERSION,
        )
        db.add(pair)
    pair.hamming_phash = hamming_phash
    pair.hamming_dhash = hamming_dhash
    pair.ocr_text_similarity = text_similarity
    pair.similarity_level = similarity_level
    pair.decision_reason = decision_reason
    await db.flush()
    return pair


async def _clear_asset_similarity(db: AsyncSession, asset: KbImageAsset) -> None:
    old_group_id = asset.similarity_group_id
    await db.execute(
        sa_delete(KbImageSimilarPair).where(
            or_(
                KbImageSimilarPair.source_asset_id == asset.id,
                KbImageSimilarPair.target_asset_id == asset.id,
            )
        )
    )
    asset.similarity_group_id = None
    asset.group_representative = False
    if old_group_id is not None:
        group = await db.scalar(
            select(KbImageSimilarityGroup).where(KbImageSimilarityGroup.id == old_group_id)
        )
        if group is not None:
            group.asset_count = int(await db.scalar(
                select(func.count(KbImageAsset.id)).where(KbImageAsset.similarity_group_id == old_group_id)
            ) or 0)
            if group.asset_count <= 0:
                group.status = "stale"


async def _ensure_high_similarity_group(
    db: AsyncSession,
    *,
    owner_id: int,
    new_asset: KbImageAsset,
    matched_asset: KbImageAsset,
) -> None:
    group_id = matched_asset.similarity_group_id or new_asset.similarity_group_id
    if group_id is None:
        group = KbImageSimilarityGroup(
            owner_id=owner_id,
            representative_asset_id=int(matched_asset.id),
            asset_count=0,
            asset_type=matched_asset.asset_type or new_asset.asset_type or "unknown",
            status="active",
        )
        db.add(group)
        await db.flush()
        group_id = int(group.id)
        matched_asset.group_representative = True
    else:
        group = await db.scalar(
            select(KbImageSimilarityGroup).where(KbImageSimilarityGroup.id == group_id)
        )
        if group is None:
            return

    matched_asset.similarity_group_id = group_id
    new_asset.similarity_group_id = group_id
    if int(matched_asset.id) == int(group.representative_asset_id or 0):
        matched_asset.group_representative = True
    new_asset.group_representative = False
    group.asset_count = int(await db.scalar(
        select(func.count(KbImageAsset.id)).where(KbImageAsset.similarity_group_id == group_id)
    ) or 0)


async def _compare_asset_with_existing(db: AsyncSession, asset: KbImageAsset) -> dict:
    result = await db.execute(
        select(KbImageAsset).where(
            KbImageAsset.owner_id == asset.owner_id,
            KbImageAsset.hash_schema_version == IMAGE_HASH_SCHEMA_VERSION,
            KbImageAsset.id != asset.id,
            or_(KbImageAsset.phash.is_not(None), KbImageAsset.dhash.is_not(None)),
        )
    )
    other_assets = result.scalars().all()
    pair_count = 0
    high_count = 0
    suspected_count = 0
    asset_ocr = ((asset.diagnostics_json or {}).get("ocr_text_normalized") or "")
    for other in other_assets:
        phash_distance = hamming_distance(asset.phash, other.phash)
        dhash_distance = hamming_distance(asset.dhash, other.dhash)
        other_ocr = ((other.diagnostics_json or {}).get("ocr_text_normalized") or "")
        text_similarity = ocr_text_similarity(asset_ocr, other_ocr)
        level, reason = classify_similarity(
            hamming_phash=phash_distance,
            hamming_dhash=dhash_distance,
            text_similarity=text_similarity,
        )
        if level == "different":
            continue
        await _upsert_pair(
            db,
            owner_id=asset.owner_id,
            source_asset_id=int(asset.id),
            target_asset_id=int(other.id),
            hamming_phash=phash_distance,
            hamming_dhash=dhash_distance,
            text_similarity=text_similarity,
            similarity_level=level,
            decision_reason=reason,
        )
        pair_count += 1
        if level == "high":
            high_count += 1
            await _ensure_high_similarity_group(
                db,
                owner_id=asset.owner_id,
                new_asset=asset,
                matched_asset=other,
            )
        else:
            suspected_count += 1
    return {"pairs": pair_count, "high": high_count, "suspected": suspected_count}


async def record_document_image_assets(
    db: AsyncSession,
    *,
    owner_id: int,
    document_id: int,
    file_id: int,
    page_images: dict[int, bytes],
    page_preprocess: dict[int, dict] | None = None,
    asset_type: str = "page_render",
) -> dict:
    """Persist image fingerprints and near-duplicate evidence as a side stage."""
    if not page_images:
        return {"assets": 0, "pairs": 0, "high": 0, "suspected": 0, "status": "skipped"}

    assets: list[KbImageAsset] = []
    for page, image_bytes in sorted(page_images.items()):
        if not image_bytes:
            continue
        assets.append(await _upsert_asset(
            db,
            owner_id=owner_id,
            document_id=document_id,
            file_id=file_id,
            page=int(page),
            image_bytes=image_bytes,
            asset_type=asset_type,
            preprocess=(page_preprocess or {}).get(int(page)),
        ))

    for asset in assets:
        await _clear_asset_similarity(db, asset)

    totals = {"pairs": 0, "high": 0, "suspected": 0}
    for asset in assets:
        counts = await _compare_asset_with_existing(db, asset)
        for key in totals:
            totals[key] += int(counts.get(key, 0))

    await db.commit()
    return {
        "assets": len(assets),
        **totals,
        "status": "done" if assets else "skipped",
        "hash_schema_version": IMAGE_HASH_SCHEMA_VERSION,
        "calc_version": IMAGE_SIMILARITY_CALC_VERSION,
        "vlm_reuse": False,
    }
