"""PostgresCheckpointSaver — lightweight per-round checkpoint persistence.

Saves execution state (messages, tool_events, timeline, pending_events)
after each tool round.  Worker crashes can resume from the last checkpoint
without losing the conversation turn.

Design:
  - Single table ``agent_checkpoints`` with JSONB channel_values.
  - No DeltaChannel / Pregel / Effect framework (not needed for tool-loop).
  - UPSERT semantics: ``put`` is idempotent.
  - ``owner_id`` stored as a dedicated column (NOT NULL), never buried in JSON.
  - Column name is ``extra_meta``, not ``metadata`` (SQLAlchemy reserved word).
  - Uses raw SQL via connection execute to avoid text() bind-param confusion
    with ``:number`` patterns inside JSON values.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.agent").getChild("runtime.checkpointer")


class PostgresCheckpointSaver:
    """Checkpoint saver backed by the agent_checkpoints table.

    Usage::

        saver = PostgresCheckpointSaver()
        await saver.put(db, conversation_id, owner_id, checkpoint_id,
                        step, channel_values, parent_checkpoint_id=None)
        cp = await saver.get_tuple(db, conversation_id, checkpoint_id=None)
        checkpoints = await saver.list(db, conversation_id)
    """

    async def put(
        self,
        db: AsyncSession,
        conversation_id: int,
        owner_id: int,
        checkpoint_id: str,
        step: int,
        channel_values: dict,
        parent_checkpoint_id: str | None = None,
        extra_meta: dict | None = None,
        workflow_run_id: int | None = None,
        workflow_step_id: int | None = None,
        agent_run_id: str | None = None,
        checkpoint_type: str | None = None,
        resume_cursor: dict | None = None,
    ) -> None:
        """Upsert a checkpoint record.

        Uses raw SQL via ``connection.exec_driver_sql`` with
        positional ``$N`` parameters so JSON strings containing
        ``:number`` don't confuse the parser.
        """
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        vals = json.dumps(channel_values, ensure_ascii=False, default=str)
        meta = json.dumps(extra_meta or {}, ensure_ascii=False, default=str)
        cursor = json.dumps(resume_cursor or {}, ensure_ascii=False, default=str)

        conn = await db.connection()
        await conn.exec_driver_sql(
            "INSERT INTO agent_checkpoints "
            "(conversation_id, checkpoint_id, parent_checkpoint_id, step, "
            " channel_values, extra_meta, owner_id, workflow_run_id, "
            " workflow_step_id, agent_run_id, checkpoint_type, resume_cursor, "
            " created_at, updated_at) "
            "VALUES ($1::bigint, $2::varchar, $3::varchar, $4::integer, "
            "  CAST($5 AS jsonb), CAST($6 AS jsonb), $7::integer, "
            "  $8::bigint, $9::bigint, $10::varchar, $11::varchar, "
            "  CAST($12 AS jsonb), $13, $13) "
            "ON CONFLICT (conversation_id, checkpoint_id) DO UPDATE SET "
            "  step = EXCLUDED.step, "
            "  channel_values = EXCLUDED.channel_values, "
            "  extra_meta = EXCLUDED.extra_meta, "
            "  workflow_run_id = EXCLUDED.workflow_run_id, "
            "  workflow_step_id = EXCLUDED.workflow_step_id, "
            "  agent_run_id = EXCLUDED.agent_run_id, "
            "  checkpoint_type = EXCLUDED.checkpoint_type, "
            "  resume_cursor = EXCLUDED.resume_cursor, "
            "  updated_at = NOW()",
            [
                (conversation_id, checkpoint_id, parent_checkpoint_id, step,
                 vals, meta, owner_id, workflow_run_id, workflow_step_id,
                 agent_run_id, checkpoint_type, cursor, now),
            ],
        )
        await db.commit()

    async def get_tuple(
        self,
        db: AsyncSession,
        conversation_id: int,
        checkpoint_id: str | None = None,
    ) -> dict | None:
        """Return the checkpoint dict, or None.

        If *checkpoint_id* is given, returns that exact checkpoint.
        Otherwise returns the latest (highest step) for the conversation.
        """
        if checkpoint_id:
            result = await db.execute(text(
                "SELECT checkpoint_id, parent_checkpoint_id, step, "
                "       channel_values, extra_meta, owner_id, "
                "       workflow_run_id, workflow_step_id, agent_run_id, "
                "       checkpoint_type, resume_cursor "
                "FROM agent_checkpoints "
                "WHERE conversation_id = :conv_id AND checkpoint_id = :cp_id"
            ), {"conv_id": conversation_id, "cp_id": checkpoint_id})
        else:
            result = await db.execute(text(
                "SELECT checkpoint_id, parent_checkpoint_id, step, "
                "       channel_values, extra_meta, owner_id, "
                "       workflow_run_id, workflow_step_id, agent_run_id, "
                "       checkpoint_type, resume_cursor "
                "FROM agent_checkpoints "
                "WHERE conversation_id = :conv_id "
                "ORDER BY step DESC LIMIT 1"
            ), {"conv_id": conversation_id})
        row = result.fetchone()
        if not row:
            return None
        return {
            "checkpoint_id": row[0],
            "parent_checkpoint_id": row[1],
            "step": row[2],
            "channel_values": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
            "extra_meta": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
            "owner_id": row[5],
            "workflow_run_id": row[6],
            "workflow_step_id": row[7],
            "agent_run_id": row[8],
            "checkpoint_type": row[9],
            "resume_cursor": row[10] if isinstance(row[10], dict) else json.loads(row[10] or "{}"),
        }

    async def list(
        self,
        db: AsyncSession,
        conversation_id: int,
        limit: int = 20,
    ) -> list[dict]:
        """List checkpoints for a conversation, newest first."""
        result = await db.execute(text(
            "SELECT checkpoint_id, parent_checkpoint_id, step, "
            "       channel_values, extra_meta, owner_id, "
            "       workflow_run_id, workflow_step_id, agent_run_id, "
            "       checkpoint_type, resume_cursor "
            "FROM agent_checkpoints "
            "WHERE conversation_id = :conv_id "
            "ORDER BY step DESC LIMIT :lim"
        ), {"conv_id": conversation_id, "lim": limit})
        rows = []
        for row in result.fetchall():
            rows.append({
                "checkpoint_id": row[0],
                "parent_checkpoint_id": row[1],
                "step": row[2],
                "channel_values": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
                "extra_meta": row[4] if isinstance(row[4], dict) else json.loads(row[4] or "{}"),
                "owner_id": row[5],
                "workflow_run_id": row[6],
                "workflow_step_id": row[7],
                "agent_run_id": row[8],
                "checkpoint_type": row[9],
                "resume_cursor": row[10] if isinstance(row[10], dict) else json.loads(row[10] or "{}"),
            })
        return rows

    @staticmethod
    def new_checkpoint_id() -> str:
        """Generate a new checkpoint UUID string."""
        return str(uuid.uuid4())
