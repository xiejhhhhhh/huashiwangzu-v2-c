"""Direct integration tests for PostgresCheckpointSaver + checkpoint model.

Tests the checkpointer independently of the model gateway (which has a
pre-existing timeout issue).  Covers:
  1. DB schema: table exists, owner_id NOT NULL, no metadata column
  2. Saver put/get_tuple/list
  3. Policy switch exists and defaults to False
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so 'modules' can be imported
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from modules.agent.backend.runtime.checkpointer import PostgresCheckpointSaver
from modules.agent.backend.runtime.runtime_policy import RuntimePolicy


# ── Schema tests (direct psql via SQLAlchemy) ───────────────────────────────

@pytest.mark.asyncio
async def test_table_exists():
    """agent_checkpoints table must exist."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'agent_checkpoints'"
        ))
        assert rows.fetchone() is not None, "agent_checkpoints table must exist"


@pytest.mark.asyncio
async def test_owner_id_not_null():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'agent_checkpoints' AND column_name = 'owner_id'"
        ))
        row = rows.fetchone()
        assert row is not None, "owner_id column must exist"
        assert row[0] == "NO", "owner_id must be NOT NULL"


@pytest.mark.asyncio
async def test_no_metadata_column():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'agent_checkpoints' AND column_name = 'metadata'"
        ))
        assert rows.fetchone() is None, "metadata column must NOT exist"


@pytest.mark.asyncio
async def test_extra_meta_column_exists():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'agent_checkpoints' AND column_name = 'extra_meta'"
        ))
        assert rows.fetchone() is not None, "extra_meta column must exist"


@pytest.mark.asyncio
async def test_unique_constraint():
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name = 'agent_checkpoints' AND constraint_type = 'UNIQUE'"
        ))
        names = [r[0] for r in rows.fetchall()]
        assert any("checkpoint" in n for n in names), \
            "Unique constraint on (conversation_id, checkpoint_id) must exist"


# ── Saver tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_put_and_get_tuple():
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        saver = PostgresCheckpointSaver()
        conv_id = 999001
        owner_id = 42
        cp_id = str(uuid.uuid4())
        channel_vals = {
            "messages": [{"role": "user", "content": "hi"}],
            "tool_events": [],
            "timeline": [],
            "pending_events": [],
            "event_round": 1,
            "persisted_event_count": 0,
        }
        await saver.put(db, conv_id, owner_id, cp_id, step=1, channel_values=channel_vals)

        fetched = await saver.get_tuple(db, conv_id, cp_id)
        assert fetched is not None
        assert fetched["checkpoint_id"] == cp_id
        assert fetched["owner_id"] == owner_id
        assert fetched["step"] == 1
        assert fetched["channel_values"]["messages"][0]["content"] == "hi"


@pytest.mark.asyncio
async def test_get_latest():
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        saver = PostgresCheckpointSaver()
        conv_id = 999002
        owner_id = 42
        cp1 = str(uuid.uuid4())
        cp2 = str(uuid.uuid4())
        base = {"messages": [], "tool_events": [], "timeline": [],
                "pending_events": [], "event_round": 0, "persisted_event_count": 0}
        await saver.put(db, conv_id, owner_id, cp1, step=1,
                        channel_values={**base, "messages": [{"r": 1}]})
        await saver.put(db, conv_id, owner_id, cp2, step=2,
                        channel_values={**base, "messages": [{"r": 2}]})

        latest = await saver.get_tuple(db, conv_id)
        assert latest is not None
        assert latest["step"] == 2
        assert latest["channel_values"]["messages"][0]["r"] == 2


@pytest.mark.asyncio
async def test_list():
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        saver = PostgresCheckpointSaver()
        conv_id = 999003
        owner_id = 42
        base = {"messages": [], "tool_events": [], "timeline": [],
                "pending_events": [], "event_round": 0, "persisted_event_count": 0}
        cps = []
        for i in range(3):
            cid = str(uuid.uuid4())
            cps.append(cid)
            await saver.put(db, conv_id, owner_id, cid, step=i + 1,
                            channel_values={**base, "event_round": i})

        results = await saver.list(db, conv_id, limit=10)
        assert len(results) >= 3
        assert results[0]["step"] == 3


@pytest.mark.asyncio
async def test_owner_id_stored():
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        saver = PostgresCheckpointSaver()
        conv_id = 999004
        owner_id = 99
        cp_id = str(uuid.uuid4())
        await saver.put(db, conv_id, owner_id, cp_id, step=1,
                        channel_values={"messages": [], "tool_events": [],
                                        "timeline": [], "pending_events": [],
                                        "event_round": 0, "persisted_event_count": 0})
        fetched = await saver.get_tuple(db, conv_id, cp_id)
        assert fetched is not None
        assert fetched["owner_id"] == 99


# ── Policy tests ────────────────────────────────────────────────────────────

class TestRuntimePolicy:
    def test_switch_exists(self):
        policy = RuntimePolicy.default()
        assert hasattr(policy, "enable_checkpointer")
        assert hasattr(policy, "checkpoint_interval")

    def test_default_off(self):
        policy = RuntimePolicy.default()
        assert policy.enable_checkpointer is False

    def test_can_enable(self):
        policy = RuntimePolicy.default()
        policy.enable_checkpointer = True
        assert policy.enable_checkpointer is True
