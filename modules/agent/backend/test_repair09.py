"""Behavioral tests for Agent 底座维修 09 — repair round 1.

Covers the P0/P1 fixes that the original delivery missed.
Each test targets one verified failure mode from the验收退回.
"""
import json

import pytest
from app.database import AsyncSessionLocal
from sqlalchemy import text as sa_text

from modules.agent.backend.engine.budget_allocator import (
    estimate_one_message,
    get_effective_context_budget,
)
from modules.agent.backend.engine.compressor import _find_tool_pairs
from modules.agent.backend.engine.workflow_recipe_service import _text_intent_similarity
from modules.agent.backend.runtime.task_sink import RuntimeTaskSink
from modules.agent.backend.services.profile_evolve import _make_fingerprint

# ── Test 1: record_turn() INSERT + replay upsert via pg_insert() ─────────

@pytest.mark.asyncio
async def test_record_turn_typed_jsonb_upsert():
    """P0-1: record_turn() uses pg_insert() with typed JSONB binds.

    This test exercises the actual pg_insert() + on_conflict_do_update()
    path to prove it works with asyncpg — as opposed to the old
    ``sa_text(... :tool_calls::jsonb ...)`` syntax that crashes.
    """
    from modules.agent.backend.services.trajectory_service import record_turn

    async with AsyncSessionLocal() as db:
        try:
            # Use negative IDs to avoid colliding with production data
            conv_id = -999901
            owner_id = -999901

            # First insert
            r1 = await record_turn(
                db, conversation_id=conv_id, owner_id=owner_id,
                session_id="test-s9r1", turn_index=0,
                user_input="first turn",
                tool_calls=[{"name": "tool_a", "arguments": {"x": 1}}],
                tool_results=[{"name": "tool_a", "result": {"success": True, "data": {"file_id": 42}}}],
                assistant_response="First response",
                error_occurred=False,
                duration_ms=100.0, token_count=500,
            )
            assert r1["recorded"] is True, f"First insert failed: {r1}"
            assert r1["id"] is not None

            # Replay (same conv + turn) → upsert
            r2 = await record_turn(
                db, conversation_id=conv_id, owner_id=owner_id,
                session_id="test-s9r1", turn_index=0,
                user_input="updated input",
                tool_calls=[{"name": "tool_b"}],
                tool_results=[{"name": "tool_b", "result": {"success": True}}],
                assistant_response="Updated response",
                error_occurred=False,
                duration_ms=200.0, token_count=600,
            )
            assert r2["recorded"] is True, f"Upsert failed: {r2}"
            # Upsert returns the same id (same row, updated)
            assert r2["id"] == r1["id"], (
                f"Upsert should return same id, got {r2['id']} != {r1['id']}"
            )

            # Raw SQL readback (without ::jsonb) to verify values
            row = await db.execute(sa_text(
                "SELECT user_input, tool_calls::text, tool_results::text, "
                "assistant_response, duration_ms, token_count "
                "FROM agent_trajectory_records WHERE id=:rid"
            ), {"rid": r1["id"]})
            r = row.one()
            assert r[0] == "updated input"
            assert json.loads(r[1])[0]["name"] == "tool_b"
            assert json.loads(r[2])[0]["name"] == "tool_b"
            assert r[3] == "Updated response"
            assert r[4] == 200.0
            assert r[5] == 600
        finally:
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                await db.execute(sa_text(
                    "DELETE FROM agent_trajectory_records WHERE owner_id=:oid",
                ), {"oid": owner_id})
                await db.commit()
            except Exception:
                await db.rollback()


# ── Test 2: Two distinct turn_index values → two rows ───────────────────

@pytest.mark.asyncio
async def test_two_turns_two_trajectories():
    """P0-3: Two distinct user turns produce two trajectory rows (not overwrite)."""
    from modules.agent.backend.services.trajectory_service import record_turn

    async with AsyncSessionLocal() as db:
        try:
            conv_id = -999902
            owner_id = -999902

            r1 = await record_turn(
                db, conv_id, owner_id, "test-s9r2", 0,
                user_input="turn 0",
                tool_calls=[{"name": "tool_a"}],
                assistant_response="resp 0",
            )
            assert r1["recorded"] is True

            r2 = await record_turn(
                db, conv_id, owner_id, "test-s9r2", 1,
                user_input="turn 1",
                tool_calls=[{"name": "tool_b"}],
                assistant_response="resp 1",
            )
            assert r2["recorded"] is True

            assert r1["turn_index"] != r2["turn_index"]
            assert r1["id"] != r2["id"], "Two turns must have different IDs"

            cnt = await db.execute(sa_text(
                "SELECT count(*) FROM agent_trajectory_records "
                "WHERE conversation_id=:cid AND owner_id=:oid",
            ), {"cid": conv_id, "oid": owner_id})
            assert cnt.scalar() == 2, "Should have 2 rows for 2 turns"
        finally:
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                await db.execute(sa_text(
                    "DELETE FROM agent_trajectory_records WHERE owner_id=:oid",
                ), {"oid": owner_id})
                await db.commit()
            except Exception:
                await db.rollback()


# ── Test 3: Unique index exists in the agent_trajectory_records table ────

@pytest.mark.asyncio
async def test_trajectory_unique_index_exists():
    """P0-2: uq_trajectory_conv_turn unique index must exist."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(sa_text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename='agent_trajectory_records' "
            "AND indexname='uq_trajectory_conv_turn'"
        ))
        assert result.scalar_one_or_none() is not None, (
            "Unique index uq_trajectory_conv_turn not found"
        )


# ── Test 4: Error + rollback leaves session usable ───────────────────────

@pytest.mark.asyncio
async def test_session_rollback_after_error():
    """P0-4: record_turn() rolls back its own failed transaction."""
    from modules.agent.backend.services.trajectory_service import record_turn

    async with AsyncSessionLocal() as db:
        failed = await record_turn(
            db,
            conversation_id=-999904,
            owner_id=-999904,
            session_id="rollback-test",
            turn_index=None,
            user_input="must fail",
        )
        assert failed["recorded"] is False
        r2 = await db.execute(sa_text("SELECT 1"))
        assert r2.scalar() == 1, "record_turn must leave session usable"
        await db.rollback()


# ── Test 5: Two different-phrasing text inputs → high similarity ─────────

def test_text_intent_similarity_matches_same_intent():
    """P1-1: _text_intent_similarity() matches same intent in different words."""
    score = _text_intent_similarity("Create an Excel file with sales data",
                                     "Generate a xlsx spreadsheet for sales")
    assert score >= 0.2, f"Similar intent should score >=0.2, got {score}"

    score2 = _text_intent_similarity("What is the weather today",
                                     "Delete all files")
    assert score2 < 0.3, f"Different intents should score <0.3, got {score2}"


# ── Test 6: Failed tool result → not eligible for workflow mining ────────

@pytest.mark.asyncio
async def test_check_tool_success():
    """P1-2: check_tool_success() correctly identifies failures."""
    sink = RuntimeTaskSink(conversation_id=0, owner_id=0)

    # All succeed
    ok_events = [
        {"type": "tool_result", "result": {"success": True, "data": {"file_id": 1}}},
    ]
    assert sink.check_tool_success(ok_events) is True

    # Top-level error
    err_events = [
        {"type": "tool_result", "result": {"success": False, "error": "permission denied"}},
    ]
    assert sink.check_tool_success(err_events) is False

    # Envelope error
    envelope_err = [
        {"type": "tool_result", "result": {"success": True, "data": {"success": False, "error": "inner fail"}}},
    ]
    assert sink.check_tool_success(envelope_err) is False

    # Empty result list = no tool calls = success
    assert sink.check_tool_success([]) is True

    # Event-level error
    event_err = [
        {"type": "tool_call", "name": "test"},
        {"event_type": "error", "payload": {"message": "model error"}},
    ]
    assert sink.check_tool_success(event_err) is False


# ── Test 7: Large tool arguments → estimate is accurate ──────────────────

def test_estimate_one_message_includes_tool_calls():
    """P1-3: estimate_one_message() must count tool_calls, arguments, role."""
    msg_no_tools = {"role": "user", "content": "hello"}
    tokens_no_tools = estimate_one_message(msg_no_tools)
    assert tokens_no_tools > 0

    # Message with large tool arguments
    big_args = {f"key_{i}": "x" * 500 for i in range(10)}
    msg_with_tools = {
        "role": "assistant",
        "content": "Let me call a tool",
        "tool_calls": [
            {
                "function": {"name": "big_tool", "arguments": big_args},
                "id": "call_12345",
            }
        ],
    }
    tokens_with = estimate_one_message(msg_with_tools)
    tokens_no = estimate_one_message({"role": "assistant", "content": "Let me call a tool"})
    assert tokens_with > tokens_no, (
        f"Tool call arguments not counted: {tokens_with} <= {tokens_no}"
    )
    # The large args should dominate the estimate
    assert tokens_with > 1000, f"Large arguments not reflected: {tokens_with}"


# ── Test 8: No orphan tool pairs in compressor ───────────────────────────

def test_find_tool_pairs_by_tool_call_id():
    """P1-4: _find_tool_pairs() must pair results with calls via tool_call_id."""
    events = [
        {"event_type": "user_msg", "payload": {"content": "hello"}},
        {"event_type": "tool_call", "llm_response_id": "round_0",
         "payload": {"tool_call_id": "tc_1", "function": {"name": "search"}}},
        {"event_type": "tool_result", "llm_response_id": None,
         "payload": {"tool_call_id": "tc_1", "content": "results"}},
        {"event_type": "assistant_msg", "payload": {"content": "done"}},
    ]

    pairs = _find_tool_pairs(events)
    assert len(pairs) >= 1, f"Expected at least 1 pair, got {pairs}"

    # The tool_call and tool_result should both be inside the paired range
    for pair_start, pair_end in pairs:
        for idx in range(pair_start, pair_end):
            etype = events[idx].get("event_type", "")
            assert etype in ("tool_call", "tool_result"), (
                f"Pair contains non-tool event {etype} at index {idx}"
            )


# ── Test 9: Completion evidence four cases ───────────────────────────────

@pytest.mark.asyncio
async def test_completion_evidence_cases():
    """P1-5: Four evidence scenarios produce correct results."""
    sink = RuntimeTaskSink(conversation_id=0, owner_id=0)

    # Case 1: Write success, no read → read_back_verified=False
    ev1 = [
        {"type": "tool_call", "name": "desktop-tools__create_file",
         "tool_call_id": "c1", "arguments": {"file_name": "test.txt"}},
    ]
    tr1 = [
        {"type": "tool_result", "tool_call_id": "c1",
         "result": {"success": True, "data": {"file_id": 100}}},
    ]
    evidence1 = await sink.generate_completion_evidence(ev1, tr1)
    write_ev = [e for e in evidence1 if e.get("tool_name", "").endswith("create_file")]
    assert len(write_ev) == 1
    assert write_ev[0]["tool_reported_success"] is True
    assert write_ev[0]["read_back_verified"] is False

    # Case 2: Write + read that fails → read_back_verified=False
    ev2 = [
        {"type": "tool_call", "name": "desktop-tools__update_file",
         "tool_call_id": "c2", "arguments": {"file_id": 100}},
        {"type": "tool_call", "name": "desktop-tools__get_file_detail",
         "tool_call_id": "c3", "arguments": {"file_id": 100}},
    ]
    tr2 = [
        {"type": "tool_result", "tool_call_id": "c2",
         "result": {"success": True, "data": {"file_id": 100}}},
        {"type": "tool_result", "tool_call_id": "c3",
         "result": {"success": False, "error": "permission denied"}},
    ]
    evidence2 = await sink.generate_completion_evidence(ev2, tr2)
    update_failed = [e for e in evidence2 if "update_file" in e.get("tool_name", "")]
    assert len(update_failed) == 1
    assert update_failed[0]["read_back_verified"] is False

    # Case 3: Write + read succeeds and content matches → read_back_verified=True
    ev3 = [
        {"type": "tool_call", "name": "desktop-tools__update_file",
         "tool_call_id": "c4", "arguments": {"file_id": 101, "content": "updated"}},
        {"type": "tool_call", "name": "desktop-tools__get_file_detail",
         "tool_call_id": "c5", "arguments": {"file_id": 101}},
    ]
    tr3 = [
        {"type": "tool_result", "tool_call_id": "c4",
         "result": {"success": True, "data": {"file_id": 101}}},
        {"type": "tool_result", "tool_call_id": "c5",
         "result": {"success": True, "data": {"file_id": 101, "content": "updated"}}},
    ]
    evidence3 = await sink.generate_completion_evidence(ev3, tr3)
    update_items = [e for e in evidence3 if "update_file" in e.get("tool_name", "")]
    assert len(update_items) == 1
    assert update_items[0]["read_back_verified"] is True

    # Same artifact but mismatched content is not verified.
    tr3[1]["result"]["data"]["content"] = "old"
    mismatch = await sink.generate_completion_evidence(ev3, tr3)
    mismatch_items = [e for e in mismatch if "update_file" in e.get("tool_name", "")]
    assert len(mismatch_items) == 1
    assert mismatch_items[0]["read_back_verified"] is False

    # Case 4: Write-only (no read tool at all) → read_back_verified=False
    ev4 = [
        {"type": "tool_call", "name": "desktop-tools__generate_report",
         "tool_call_id": "c6", "arguments": {"title": "report"}},
    ]
    tr4 = [
        {"type": "tool_result", "tool_call_id": "c6",
         "result": {"success": True, "data": {"file_id": 102}}},
    ]
    evidence4 = await sink.generate_completion_evidence(ev4, tr4)
    for item in evidence4:
        assert item["read_back_verified"] is False, (
            f"Write-only should not be verified: {item}"
        )
    # Case 5: Live runtime shape may have no tool_call_id; ordered fallback
    # must still correlate calls/results instead of returning empty evidence.
    runtime_shape = [
        {"type": "tool_call", "name": "desktop-tools__update_file",
         "arguments": {"file_id": 103, "content": "new"}},
        {"type": "tool_result", "name": "desktop-tools__update_file",
         "result": {"success": True, "data": {"file_id": 103}}},
        {"type": "tool_call", "name": "desktop-tools__read_file",
         "arguments": {"file_id": 103}},
        {"type": "tool_result", "name": "desktop-tools__read_file",
         "result": {"success": True, "data": {"file_id": 103, "content": "old"}}},
    ]
    runtime_evidence = await sink.generate_completion_evidence(
        runtime_shape,
        [e for e in runtime_shape if e["type"] == "tool_result"],
    )
    runtime_items = [e for e in runtime_evidence if "update_file" in e.get("tool_name", "")]
    assert len(runtime_items) == 1
    assert runtime_items[0]["artifact_ids"] == ["103"]
    assert runtime_items[0]["tool_reported_success"] is True
    assert runtime_items[0]["read_back_verified"] is False


# ── Test 10: Profile signal fingerprint dedup ────────────────────────────

@pytest.mark.asyncio
async def test_profile_signal_fingerprint_dedup():
    """P1-6: Different message IDs produce different fingerprints;
    same message IDs + same item produce identical fingerprints.
    """
    fp1 = _make_fingerprint([100, 101], "likes to ask follow-up questions")
    fp2 = _make_fingerprint([100, 101], "likes to ask follow-up questions")
    fp3 = _make_fingerprint([200, 201], "likes to ask follow-up questions")

    assert fp1 == fp2, "Same inputs must produce same fingerprint"
    assert fp1 != fp3, "Different message IDs must produce different fingerprint"


# ── Test 11: Text intent similarity works cross-phrasing ─────────────────

def test_text_intent_similarity():
    """P1-1: _text_intent_similarity() matches same intent in different words."""
    from modules.agent.backend.engine.workflow_recipe_service import _text_intent_similarity

    score1 = _text_intent_similarity("Create an Excel file", "Generate a xlsx spreadsheet")
    assert score1 >= 0.2, f"Similar intent should score >=0.2, got {score1}"

    score2 = _text_intent_similarity("What is the weather today", "Delete all files")
    assert score2 < 0.3, f"Different intents should score <0.3, got {score2}"


# ── Test 12: get_effective_context_budget returns 48k when null ──────────

@pytest.mark.asyncio
async def test_get_effective_context_budget():
    """Budget: null model config yields 48k agent default."""
    budget, source = get_effective_context_budget("non_existent_model")
    assert budget == 48000, f"Expected 48000 for unknown model, got {budget}"
    assert source == "agent_default", f"Expected agent_default source, got {source}"
