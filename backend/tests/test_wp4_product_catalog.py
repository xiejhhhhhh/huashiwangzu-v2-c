"""WP4 Product Catalog + Content Open Resolver 测试。

覆盖：
1. 首批 10 个 Product 都能从 products/*/product.json 加载
2. Catalog 只返回 Product（kind=products），不含 parser 身份
3. 扩展名关联能命中 office/text
4. createDraft 产生 source-less package + canonical_json
5. autosave 新增 version 且 CAS 冲突可感知
6. Desktop state expected_version CAS
"""
from __future__ import annotations

import uuid

import app.main  # noqa: F401
import pytest
from app.core.exceptions import ConflictError
from app.database import AsyncSessionLocal
from app.models.content import ContentPackage, ContentPackageVersion
from app.models.user import User
from app.schemas.product import OpenContentIntentV1, OpenContentSource
from app.services import office_workspace_service as office_svc
from app.services.content_edit_lease_service import acquire_lease, release_lease
from app.services.content_open_resolver import resolve_open_content
from app.services.desktop_state_service import save_state
from app.services.product_catalog_service import (
    FIRST_PARTY_PRODUCT_IDS,
    find_associations_for_extension,
    list_effective_products,
    list_product_manifests,
)
from sqlalchemy import delete

OWNER_ID = 4


async def _user() -> User:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, OWNER_ID)
        assert user is not None, "seed user 4 missing"
        return user


@pytest.mark.asyncio
async def test_first_party_products_loaded():
    manifests = list_product_manifests()
    ids = {m["productId"] for m in manifests}
    for pid in FIRST_PARTY_PRODUCT_IDS:
        assert pid in ids, f"missing product {pid}"
    # Gate4：不能把 parser 当 product
    banned = {"docx-parser", "pdf-parser", "pptx-parser", "xlsx-parser", "image-vision"}
    assert ids.isdisjoint(banned)


@pytest.mark.asyncio
async def test_catalog_returns_products_only():
    user = await _user()
    async with AsyncSessionLocal() as db:
        catalog = await list_effective_products(db, user)
    assert catalog["kind"] == "products"
    assert catalog["count"] >= 10
    for item in catalog["items"]:
        assert item.get("productId")
        assert item.get("entryComponentKey")
        assert "parser" not in (item.get("productId") or "")
        # 无 appKey 四职合一字段
        assert "app_id" not in item


def test_extension_associations_prefer_office_and_text():
    docx = find_associations_for_extension("docx")
    assert docx, "docx should map to a product"
    assert docx[0]["productId"] == "office"

    txt = find_associations_for_extension("txt")
    assert txt
    assert txt[0]["productId"] in {"text", "office", "files"}


@pytest.mark.asyncio
async def test_create_draft_and_autosave_version_chain():
    package_id = None
    try:
        async with AsyncSessionLocal() as db:
            draft = await office_svc.create_draft(
                db,
                owner_id=OWNER_ID,
                product_id="office",
                extension="docx",
                title=f"draft-{uuid.uuid4().hex[:8]}",
            )
            package_id = draft["packageId"]
            assert draft["fileId"] is None
            assert draft["versionId"]
            ver1 = draft["versionId"]

            pkg = await db.get(ContentPackage, package_id)
            assert pkg is not None
            assert pkg.source_file_id is None
            v = await db.get(ContentPackageVersion, ver1)
            assert v is not None
            assert v.canonical_json

            saved = await office_svc.save_package(
                db,
                package_id=package_id,
                owner_id=OWNER_ID,
                expected_version_id=ver1,
                lock_token=None,
                content=None,
                summary="autosave-1",
                autosave=True,
            )
            assert saved["versionId"] != ver1
            assert saved["autosave"] is True

            with pytest.raises(ConflictError):
                await office_svc.save_package(
                    db,
                    package_id=package_id,
                    owner_id=OWNER_ID,
                    expected_version_id=ver1,  # stale
                    lock_token=None,
                    content=None,
                    autosave=True,
                )
    finally:
        if package_id:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(ContentPackageVersion).where(
                        ContentPackageVersion.package_id == package_id
                    )
                )
                await db.execute(
                    delete(ContentPackage).where(ContentPackage.id == package_id)
                )
                await db.commit()


@pytest.mark.asyncio
async def test_edit_lease_acquire_and_release():
    package_id = None
    try:
        async with AsyncSessionLocal() as db:
            draft = await office_svc.create_draft(
                db, owner_id=OWNER_ID, title="lease-test", extension="md",
            )
            package_id = draft["packageId"]
            lease = await acquire_lease(
                db, package_id=package_id, holder_id=OWNER_ID, base_version_id=draft["versionId"],
            )
            assert lease["token"]
            released = await release_lease(
                db, package_id=package_id, holder_id=OWNER_ID, token=lease["token"],
            )
            assert released["released"] is True
    finally:
        if package_id:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(ContentPackageVersion).where(
                        ContentPackageVersion.package_id == package_id
                    )
                )
                await db.execute(
                    delete(ContentPackage).where(ContentPackage.id == package_id)
                )
                await db.commit()


@pytest.mark.asyncio
async def test_resolver_unsupported_without_file():
    user = await _user()
    async with AsyncSessionLocal() as db:
        # 仅 deepLink + preferred product
        result = await resolve_open_content(
            db,
            user,
            OpenContentIntentV1(
                requestId="t1",
                source=OpenContentSource(deepLink="ai://chat"),
                preferredProductId="ai",
                requestedMode="view",
            ),
        )
    assert result["outcome"] in {"resolved", "unsupported"}
    if result["outcome"] == "resolved":
        assert result["productId"] == "ai"


@pytest.mark.asyncio
async def test_desktop_state_cas_conflict():
    marker = f"wp6-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        # 确保有一条状态
        state = await save_state(db, OWNER_ID, {"probe": marker, "windows": []})
        current = int(state.version)
        # 正确 CAS
        state2 = await save_state(
            db, OWNER_ID, {"probe": marker, "windows": [], "ok": True},
            expected_version=current,
        )
        assert int(state2.version) == current + 1
        # 错误 CAS
        with pytest.raises(ConflictError):
            await save_state(
                db, OWNER_ID, {"probe": "stale"},
                expected_version=current,
            )
