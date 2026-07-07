import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services import uploaded_file_runner


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return None


@pytest.mark.asyncio
async def test_sync_uploaded_file_handler_runs_off_event_loop(monkeypatch) -> None:
    loop_thread_id = threading.get_ident()
    handler_thread_id = None

    async def fake_read_uploaded_file(_db, file_id, user_id, allowed_exts):
        assert file_id == 7
        assert user_id == 4
        assert allowed_exts == {"pdf"}
        return SimpleNamespace(id=file_id, name="sample.pdf"), Path("/tmp/sample.pdf"), "pdf"

    def handler(file_id, file, full_path, ext):
        nonlocal handler_thread_id
        handler_thread_id = threading.get_ident()
        return {
            "file_id": file_id,
            "name": file.name,
            "path": str(full_path),
            "ext": ext,
        }

    monkeypatch.setattr(uploaded_file_runner, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(uploaded_file_runner, "read_uploaded_file", fake_read_uploaded_file)

    result = await uploaded_file_runner.run_uploaded_file_capability(
        {"file_id": 7},
        "user:4",
        {"pdf"},
        handler,
    )

    assert result["file_id"] == 7
    assert handler_thread_id is not None
    assert handler_thread_id != loop_thread_id


@pytest.mark.asyncio
async def test_async_uploaded_file_handler_is_awaited(monkeypatch) -> None:
    async def fake_read_uploaded_file(_db, file_id, _user_id, _allowed_exts):
        return SimpleNamespace(id=file_id, name="sample.txt"), Path("/tmp/sample.txt"), "txt"

    async def handler(file_id, file, full_path, ext):
        await asyncio.sleep(0)
        return {
            "file_id": file_id,
            "name": file.name,
            "path": str(full_path),
            "ext": ext,
        }

    monkeypatch.setattr(uploaded_file_runner, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(uploaded_file_runner, "read_uploaded_file", fake_read_uploaded_file)

    result = await uploaded_file_runner.run_uploaded_file_capability(
        {"file_id": 8},
        "user:4",
        {"txt"},
        handler,
    )

    assert result == {
        "file_id": 8,
        "name": "sample.txt",
        "path": "/tmp/sample.txt",
        "ext": "txt",
    }
