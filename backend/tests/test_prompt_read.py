"""Tests for prompt template read/render — framework layer.

Covers:
- render_template_sync (pure function, no DB)
- GET /api/prompts/templates/by-name/<name> (read-only access)
- get_template_by_name (prompt_service)
- Template not found
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.prompt_service import render_template_sync
from app.core.exceptions import NotFound


# ── Unit: render_template_sync ──────────────────────────────────────


def test_render_template_sync_no_variables():
    tpl = {"content": "Hello, world!"}
    assert render_template_sync(tpl) == "Hello, world!"


def test_render_template_sync_with_variables():
    tpl = {"content": "Hello, {{name}}! You are {{role}}."}
    result = render_template_sync(tpl, {"name": "Alice", "role": "admin"})
    assert result == "Hello, Alice! You are admin."


def test_render_template_sync_partial_variables():
    tpl = {"content": "Hello, {{name}}! {{missing}}"}
    result = render_template_sync(tpl, {"name": "Bob"})
    assert result == "Hello, Bob! {{missing}}"


def test_render_template_sync_empty_template():
    tpl = {"content": ""}
    assert render_template_sync(tpl) == ""


# ── Integration: route exists ──────────────────────────────────────


@pytest.mark.asyncio
async def test_get_template_by_name_requires_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/prompts/templates/by-name/knowledge_profile_system")
    assert resp.status_code == 401
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "Authentication required"


@pytest.mark.asyncio
async def test_get_template_by_name_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # login first
        login = await client.post("/api/login", json={"username": "admin", "password": "admin123"})
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get(
            "/api/prompts/templates/by-name/nonexistent_template_xyz",
            headers=headers,
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_template_by_name_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/api/login", json={"username": "admin", "password": "admin123"})
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get(
            "/api/prompts/templates/by-name/knowledge_profile_system",
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    tpl = data["data"]
    assert tpl["name"] == "knowledge_profile_system"
    assert "你是企业文档分析专家" in tpl["content"]
    assert tpl["is_enabled"] is True


@pytest.mark.asyncio
async def test_get_template_by_name_viewer_can_access():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/api/login", json={"username": "viewer", "password": "admin123"})
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get(
            "/api/prompts/templates/by-name/knowledge_entity_extraction",
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "knowledge_entity_extraction"


@pytest.mark.asyncio
async def test_read_all_knowledge_templates():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post("/api/login", json={"username": "admin", "password": "admin123"})
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/prompts/templates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    templates = data["data"]
    names = [t["name"] for t in templates]
    assert "knowledge_profile_system" in names
    assert "knowledge_entity_extraction" in names
    assert "knowledge_page_fusion" in names


@pytest.mark.asyncio
async def test_render_template_through_service():
    """Integration: use prompt_service.render_template via helper."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import get_db
    from app.services.prompt_service import render_template

    async for db in get_db():
        content = await render_template(db, "knowledge_profile_system")
        assert "你是企业文档分析专家" in content
        break
