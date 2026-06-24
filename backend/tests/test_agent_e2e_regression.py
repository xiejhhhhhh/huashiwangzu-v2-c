"""Agent runtime E2E regression: live API calls against the running backend.

These tests verify the complete chain works end-to-end:
  1. Session creation + message persistence
  2. Skill file injection (structural check)
  3. Memory recall path (structural check)
  4. Hook run recording (structural check)
  5. Compression + snapshot chain (structural check)
  6. Admin endpoints (hook-lifecycle, memory-quality, compression-chain)

Prerequisites:
  - Backend running on port 33000 (read from ``backend/logs/.backend.port``)
  - Valid admin token obtained via ``POST /api/login``

Run::
    cd backend && .venv/bin/python -m pytest tests/test_agent_e2e_regression.py -v --timeout=60

This file is the main regression spine — run before/after any Agent engine
change to detect regressions.
"""

import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urljoin

import pytest
import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────

BACKEND_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = BACKEND_ROOT.parent / "modules" / "agent" / "backend"
ENGINE_DIR = AGENT_DIR / "engine"
HANDLERS_DIR = AGENT_DIR / "handlers"

_PORT_FILE = BACKEND_ROOT / "logs" / ".backend.port"
BASE_URL = f'http://127.0.0.1:{_PORT_FILE.read_text("utf-8").strip() if _PORT_FILE.exists() else "33000"}'
API = lambda p: urljoin(BASE_URL, p)


@pytest.fixture(scope="session")
def admin_token():
    """Obtain a fresh admin token for the test session."""
    resp = requests.post(
        API("/api/login"),
        json={"username": "admin", "password": "admin123"},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert data.get("success"), f"Login error: {data}"
    token = data["data"]["access_token"]
    assert token, "No token returned"
    return token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════
# 1. Session creation + message persistence
# ═══════════════════════════════════════════════════════════════════════


class TestSessionAndChat:
    """Create a real conversation and send a message — verify no 500."""

    @pytest.fixture(scope="class")
    def conversation_id(self, admin_token):
        resp = requests.post(
            API("/api/agent/conversations"),
            headers=_auth(admin_token),
            json={"title": "E2E regression test"},
            timeout=10,
        )
        assert resp.status_code == 200, f"Create conv failed: {resp.text}"
        data = resp.json()
        assert data.get("success"), f"Create conv error: {data}"
        conv_id = data["data"]["id"]
        logger.info("Created conversation %s", conv_id)
        yield conv_id
        # Cleanup
        requests.delete(
            API(f"/api/agent/conversations/{conv_id}"),
            headers=_auth(admin_token),
            timeout=10,
        )

    def test_1_create_conversation(self, conversation_id):
        assert conversation_id is not None

    def test_2_send_message_returns_sse(self, admin_token, conversation_id):
        """Send a message — must return SSE stream (200), not 500."""
        resp = requests.post(
            API("/api/agent/chat"),
            headers=_auth(admin_token),
            json={
                "conversation_id": conversation_id,
                "content": "Hello, this is an E2E regression test message.",
            },
            timeout=30,
        )
        assert resp.status_code == 200, f"Chat failed: {resp.status_code} {resp.text[:500]}"
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, f"Expected SSE, got: {content_type}"

    def test_3_conversation_has_events(self, admin_token, conversation_id):
        """Verify events were recorded."""
        resp = requests.get(
            API(f"/api/agent/admin/replay/{conversation_id}"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success"), f"Replay error: {data}"
        assert data["data"]["total_events"] >= 2, f"Expected >=2 events, got {data['data']['total_events']}"
        logger.info("Conversation %s has %d events", conversation_id, data["data"]["total_events"])


# ═══════════════════════════════════════════════════════════════════════
# 2. Skill injection check (structural — no live dir to scan)
# ═══════════════════════════════════════════════════════════════════════


class TestSkillInjection:
    """Verify skill loader handles edge cases (missing dir, empty dir, corrupt files)."""

    SKILLS_FILE = str(ENGINE_DIR / "skills_loader.py")

    def test_skills_loader_handles_missing_dir(self):
        src = Path(self.SKILLS_FILE).read_text("utf-8")
        assert "does not exist" in src
        assert "returning empty list" in src

    def test_skills_loader_handles_non_dir(self):
        src = Path(self.SKILLS_FILE).read_text("utf-8")
        assert "is not a directory" in src
        assert "returning empty list" in src

    def test_skills_loader_wraps_individual_file_errors(self):
        src = Path(self.SKILLS_FILE).read_text("utf-8")
        assert "Error loading skill from" in src


# ═══════════════════════════════════════════════════════════════════════
# 3. Memory recall path (structural)
# ═══════════════════════════════════════════════════════════════════════


class TestMemoryRecall:
    """Verify memory recall functions degrade gracefully on failure."""

    MEMORY_FILE = str(ENGINE_DIR / "layered_memory.py")

    def test_recall_returns_empty_on_failure(self):
        src = Path(self.MEMORY_FILE).read_text("utf-8")
        assert "except Exception as e" in src
        assert "return []" in src

    def test_recall_quality_db_persisted(self):
        src = Path(self.MEMORY_FILE).read_text("utf-8")
        assert "AgentRecallQuality" in src
        assert "_append_recall_quality" in src

    def test_static_memory_handles_missing_dir(self):
        src = Path(self.MEMORY_FILE).read_text("utf-8")
        assert "is_dir()" in src
        assert "return []" in src


# ═══════════════════════════════════════════════════════════════════════
# 4. Hook run recording (structural)
# ═══════════════════════════════════════════════════════════════════════


class TestHookRunPersistence:
    """Verify hook run history is persisted and observable."""

    HOOKS_FILE = str(ENGINE_DIR / "post_turn_hooks.py")

    def test_hook_runs_db_persisted(self):
        src = Path(self.HOOKS_FILE).read_text("utf-8")
        assert "AgentHookRun" in src
        assert "_append_hook_run" in src

    def test_hook_runs_individual_safe_run(self):
        src = Path(self.HOOKS_FILE).read_text("utf-8")
        assert "except Exception as exc" in src

    def test_hook_runs_has_limit(self):
        src = Path(self.HOOKS_FILE).read_text("utf-8")
        assert "_HOOK_RUN_HISTORY_MAX" in src

    def test_hook_lifecycle_endpoint_available(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/hook-lifecycle"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Hook lifecycle: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success"), f"Hook lifecycle error: {data}"
        assert "maintenance_status" in data["data"]
        assert "recent_hook_runs" in data["data"]


# ═══════════════════════════════════════════════════════════════════════
# 5. Compression + snapshot chain (structural)
# ═══════════════════════════════════════════════════════════════════════


class TestCompressionSnapshot:
    """Verify compressor and snapshot functions exist and handle failures."""

    COMPRESSOR_FILE = str(ENGINE_DIR / "compressor.py")
    SNAPSHOT_FILE = str(ENGINE_DIR / "context_snapshot.py")

    def test_compressor_has_hard_truncate_fallback(self):
        src = Path(self.COMPRESSOR_FILE).read_text("utf-8")
        assert "hard_truncate" in src.lower()

    def test_compressor_wraps_model_call_in_try(self):
        src = Path(self.COMPRESSOR_FILE).read_text("utf-8")
        assert "except Exception as e" in src
        assert "summary_text = \"\"" in src

    def test_snapshot_take_returns_none_on_failure(self):
        src = Path(self.SNAPSHOT_FILE).read_text("utf-8")
        assert "return None" in src

    def test_snapshot_enforce_retention_wraps_exceptions(self):
        src = Path(self.SNAPSHOT_FILE).read_text("utf-8")
        assert "except Exception" in src

    def test_compression_chain_admin_endpoint_returns_valid_shape(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/compression-chain/1"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Compression chain: {resp.status_code} {resp.text[:300]}"
        data = resp.json()
        assert data.get("success"), f"Compression chain error: {data}"
        assert "chain" in data["data"]


# ═══════════════════════════════════════════════════════════════════════
# 6. All admin endpoints
# ═══════════════════════════════════════════════════════════════════════


class TestAdminEndpoints:
    """Verify all admin endpoints are accessible and return correct shapes."""

    def test_memory_quality_endpoint(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/memory-quality"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Memory quality: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success")
        assert "total_recalls" in data["data"]
        assert "per_layer" in data["data"]
        assert "credibility_score" in data["data"]

    def test_hook_lifecycle_endpoint(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/hook-lifecycle"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Hook lifecycle: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success")
        assert "maintenance_status" in data["data"]
        assert "recent_hook_runs" in data["data"]
        assert isinstance(data["data"]["recent_hook_runs"], list)

    def test_overview_endpoint(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/overview"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Overview: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success")
        assert "compression" in data["data"]
        assert "conversations" in data["data"]

    def test_snapshot_admin_endpoint(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/snapshots/1"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Snapshots: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success")

    def test_replay_admin_endpoint(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/replay/1"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Replay: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success")
        assert "rounds" in data["data"]

    def test_failure_diagnostics_endpoint(self, admin_token):
        resp = requests.get(
            API("/api/agent/admin/failure-diagnostics?limit=10"),
            headers=_auth(admin_token),
            timeout=10,
        )
        assert resp.status_code == 200, f"Failure diagnostics: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert data.get("success"), f"Failure diagnostics error: {data}"
        assert "total_returned" in data["data"]
        assert "diagnostics" in data["data"]
        assert isinstance(data["data"]["diagnostics"], list)
