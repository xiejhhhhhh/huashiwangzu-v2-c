from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient

SEED_PASS = "admin123"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def _login(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/login",
        json={"username": username, "password": SEED_PASS},
    )
    response.raise_for_status()
    return response.json()["data"]["access_token"]


async def _upload_sample(
    client: AsyncClient,
    headers: dict[str, str],
    source_path: Path,
    prefix: str,
) -> int:
    filename = f"{prefix}-{uuid4().hex[:8]}-{source_path.name}"
    with source_path.open("rb") as file_obj:
        response = await client.post(
            "/api/files/upload",
            files={"file": (filename, file_obj)},
            headers=headers,
        )
    response.raise_for_status()
    return response.json()["data"]["id"]


async def _delete_file_permanently(
    client: AsyncClient,
    headers: dict[str, str],
    file_id: int,
) -> None:
    await client.post(
        "/api/files/delete",
        json={"type": "file", "id": file_id},
        headers=headers,
    )
    response = await client.get("/api/recycle/list", headers=headers)
    if response.status_code != 200:
        return
    for item in response.json()["data"]:
        if item["origin_id"] == file_id and item["item_type"] == "file":
            await client.post(
                "/api/recycle/delete-permanently",
                json={"item_type": "file", "id": item["id"]},
                headers=headers,
            )


async def _current_user_id(client: AsyncClient, headers: dict[str, str]) -> int:
    response = await client.get("/api/current-user", headers=headers)
    response.raise_for_status()
    return int(response.json()["data"]["id"])


@pytest.mark.asyncio
async def test_module_call_enforces_registered_min_role() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        viewer_headers = {
            "Authorization": f"Bearer {await _login(client, 'viewer')}",
        }
        editor_headers = {
            "Authorization": f"Bearer {await _login(client, 'editor')}",
        }

        response = await client.post(
            "/api/modules/call",
            json={
                "target_module": "terminal-tools",
                "action": "exec",
                "parameters": {"command": "pwd"},
            },
            headers=viewer_headers,
        )
        assert response.status_code == 403
        assert "Requires at least 'editor' role" in response.json()["error"]

        response = await client.post(
            "/api/modules/call",
            json={
                "target_module": "terminal-tools",
                "action": "write_file",
                "parameters": {"path": "viewer-denied.txt", "content": "no"},
            },
            headers=viewer_headers,
        )
        assert response.status_code == 403

        response = await client.post(
            "/api/modules/call",
            json={
                "target_module": "_self",
                "action": "echo",
                "parameters": {"ok": True},
            },
            headers=viewer_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["echo"] == {"ok": True}

        response = await client.post(
            "/api/modules/call",
            json={
                "target_module": "terminal-tools",
                "action": "exec",
                "parameters": {"command": "pwd"},
            },
            headers=editor_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["success"] is True


PARSER_CASES = [
    (
        "text-parser",
        "/api/text-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/text-parser/sandbox/samples/sample.txt",
    ),
    (
        "markdown-parser",
        "/api/markdown-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/markdown-parser/sandbox/samples/sample.md",
    ),
    (
        "csv-parser",
        "/api/csv-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/csv-parser/sandbox/samples/sample.csv",
    ),
    (
        "structured-parser",
        "/api/structured-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/structured-parser/sandbox/samples/sample.json",
    ),
    (
        "email-parser",
        "/api/email-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/email-parser/sandbox/samples/sample.eml",
    ),
    (
        "pdf-parser",
        "/api/pdf-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/pdf-parser/sandbox/samples/sample.pdf",
    ),
    (
        "docx-parser",
        "/api/docx-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/docx-parser/sandbox/samples/sample.docx",
    ),
    (
        "pptx-parser",
        "/api/pptx-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/pptx-parser/sandbox/samples/sample.pptx",
    ),
    (
        "xlsx-parser",
        "/api/xlsx-parser/parse",
        {"file_id": None},
        PROJECT_ROOT / "modules/xlsx-parser/sandbox/samples/sample.xlsx",
    ),
    (
        "image-vision",
        "/api/image-vision/describe",
        {"file_id": None},
        PROJECT_ROOT / "modules/image-vision/sandbox/samples/sample.png",
    ),
    (
        "excel-engine-parse",
        "/api/excel-engine/parse",
        {"file_id": None, "target_sheet": ""},
        PROJECT_ROOT / "modules/xlsx-parser/sandbox/samples/sample.csv",
    ),
    (
        "excel-engine-open",
        "/api/excel-engine/open",
        {"file_id": None, "target_sheet": ""},
        PROJECT_ROOT / "modules/xlsx-parser/sandbox/samples/sample.csv",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case_name,endpoint,payload_template,sample_path", PARSER_CASES)
async def test_file_parsers_reject_other_users_private_files(
    monkeypatch: pytest.MonkeyPatch,
    case_name: str,
    endpoint: str,
    payload_template: dict,
    sample_path: Path,
) -> None:
    if case_name == "image-vision":
        from app.services import model_services

        monkeypatch.setattr(
            model_services,
            "describe_image",
            AsyncMock(return_value="mock image description"),
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        editor_headers = {
            "Authorization": f"Bearer {await _login(client, 'editor')}",
        }
        viewer_headers = {
            "Authorization": f"Bearer {await _login(client, 'viewer')}",
        }
        file_id = await _upload_sample(
            client,
            editor_headers,
            sample_path,
            f"access-control-{case_name}",
        )
        try:
            payload = dict(payload_template)
            payload["file_id"] = file_id

            response = await client.post(endpoint, json=payload, headers=viewer_headers)
            assert response.status_code in (403, 404)

            if case_name != "excel-engine-open":
                response = await client.post(endpoint, json=payload, headers=editor_headers)
                assert response.status_code == 200
                data = response.json()["data"]
                assert data is not None
        finally:
            await _delete_file_permanently(client, editor_headers, file_id)


@pytest.mark.asyncio
async def test_docs_open_write_requires_file_edit_access() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_headers = {
            "Authorization": f"Bearer {await _login(client, 'admin')}",
        }
        editor_headers = {
            "Authorization": f"Bearer {await _login(client, 'editor')}",
        }
        editor_id = await _current_user_id(client, editor_headers)
        file_id = await _upload_sample(
            client,
            admin_headers,
            PROJECT_ROOT / "modules/text-parser/sandbox/samples/sample.txt",
            f"docs-open-write-{uuid4().hex}",
        )
        try:
            response = await client.post(
                "/api/files/share",
                json={
                    "file_id": file_id,
                    "target_user_id": editor_id,
                    "permission": "read",
                },
                headers=admin_headers,
            )
            assert response.status_code == 200

            response = await client.post(
                f"/api/docs/{file_id}/content",
                json={"content": "read share must not write"},
                headers=editor_headers,
            )
            assert response.status_code == 403

            response = await client.post(
                "/api/docs/open",
                json={"file_id": file_id, "mode": "edit"},
                headers=editor_headers,
            )
            assert response.status_code == 403

            response = await client.post(
                "/api/files/share",
                json={
                    "file_id": file_id,
                    "target_user_id": editor_id,
                    "permission": "edit",
                },
                headers=admin_headers,
            )
            assert response.status_code == 200

            response = await client.post(
                f"/api/docs/{file_id}/content",
                json={"content": "edit share can write"},
                headers=editor_headers,
            )
            assert response.status_code == 200
            assert response.json()["success"] is True

            response = await client.get(f"/api/docs/{file_id}/content", headers=admin_headers)
            assert response.status_code == 200
            assert response.json()["data"]["content"] == "edit share can write"
        finally:
            await _delete_file_permanently(client, admin_headers, file_id)


@pytest.mark.asyncio
async def test_docs_open_token_scope_enforced_for_content_file_and_revoke() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_headers = {
            "Authorization": f"Bearer {await _login(client, 'admin')}",
        }
        sample_path = PROJECT_ROOT / "modules/text-parser/sandbox/samples/sample.txt"
        file_one_id = await _upload_sample(
            client,
            admin_headers,
            sample_path,
            f"docs-open-token-one-{uuid4().hex}",
        )
        file_two_id = await _upload_sample(
            client,
            admin_headers,
            sample_path,
            f"docs-open-token-two-{uuid4().hex}",
        )
        try:
            response = await client.post(
                "/api/docs/token",
                json={"client_id": "scope-test", "scope": {"doc_ids": [file_one_id]}},
                headers=admin_headers,
            )
            assert response.status_code == 200
            token_one = response.json()["data"]["access_token"]
            open_id = response.json()["data"]["open_id"]
            token_headers = {
                "X-Client-Id": "scope-test",
                "X-Open-Id": open_id,
                "X-Access-Token": token_one,
            }

            response = await client.get(f"/api/docs/{file_one_id}/content", headers=token_headers)
            assert response.status_code == 200

            response = await client.post(
                f"/api/docs/{file_one_id}/content",
                json={"content": "read token must not write"},
                headers=token_headers,
            )
            assert response.status_code == 403

            response = await client.get(
                f"/api/docs/{file_two_id}/file",
                params={
                    "token": token_one,
                    "client_id": "scope-test",
                    "open_id": open_id,
                },
            )
            assert response.status_code == 403

            response = await client.post(
                "/api/docs/token",
                json={"client_id": "scope-test", "scope": {"doc_ids": [file_two_id]}},
                headers=admin_headers,
            )
            assert response.status_code == 200
            token_two = response.json()["data"]["access_token"]

            response = await client.post(
                f"/api/docs/{file_one_id}/revoke-tokens",
                headers=admin_headers,
            )
            assert response.status_code == 200
            assert response.json()["data"]["revoked"] == 1

            response = await client.get(
                f"/api/docs/{file_one_id}/file",
                params={
                    "token": token_one,
                    "client_id": "scope-test",
                    "open_id": open_id,
                },
            )
            assert response.status_code == 403

            response = await client.get(
                f"/api/docs/{file_two_id}/file",
                params={
                    "token": token_two,
                    "client_id": "scope-test",
                    "open_id": open_id,
                },
            )
            assert response.status_code == 200
        finally:
            await _delete_file_permanently(client, admin_headers, file_one_id)
            await _delete_file_permanently(client, admin_headers, file_two_id)
