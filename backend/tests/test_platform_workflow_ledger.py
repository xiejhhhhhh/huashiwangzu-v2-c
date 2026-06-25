"""Tests for platform workflow run ledger and resource IR skeleton.

These tests verify that:
1. The resource type catalog is accessible via API
2. Workflow definitions can be created and queried
3. Workflow run records can be created with status transitions
4. Step records can be created and linked to runs
5. The orchestrator service correctly manages lifecycle
"""
import asyncio
import logging
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.database import AsyncSessionLocal, engine
from app.models.base import Base
from app.models.platform_workflow import (
    WorkflowDefinition,
    WorkflowRunRecord,
    WorkflowStepRecord,
)
from app.schemas.platform_resource import (
    ResourceObject,
    ResourceRef,
    ResourceType,
    ResourceMetadata,
)

SEED_PASS = "admin123"
logger = logging.getLogger("v2.test_platform_workflow")


# Ensure the workflow tables exist (they may not have been created at backend startup).
async def _ensure_tables():
    async with engine.begin() as conn:
        for table in (WorkflowDefinition.__table__, WorkflowRunRecord.__table__, WorkflowStepRecord.__table__):
            await conn.run_sync(table.create, checkfirst=True)
    logger.info("Workflow tables ensured")


asyncio.run(_ensure_tables())


async def _login(client: AsyncClient) -> str:
    resp = await client.post("/api/login", json={"username": "admin", "password": SEED_PASS})
    data = resp.json()
    assert data["success"] is True
    return data["data"]["access_token"]


async def _do_cleanup():
    async with AsyncSessionLocal() as db:
        for table in (WorkflowStepRecord, WorkflowRunRecord, WorkflowDefinition):
            await db.execute(table.__table__.delete().where(table.__table__.c.id > 99999))
        await db.commit()


@pytest.fixture(scope="function")
def _cleanup_workflow_tables():
    yield
    asyncio.run(_do_cleanup())


# ── Resource IR Schema Tests (sync — no DB needed) ────────────────


class TestResourceIR:
    def test_resource_type_enum_covers_all_required(self):
        """All required resource types from the skeleton spec are present."""
        expected = {
            "prompt", "knowledge_source", "document_ir", "artifact",
            "workflow_node", "connector", "capability_binding",
        }
        actual = {t.value for t in ResourceType}
        assert expected.issubset(actual), f"Missing types: {expected - actual}"

    def test_resource_ref_roundtrip(self):
        """ResourceRef can be serialized and deserialized."""
        ref = ResourceRef(id=42, resource_type=ResourceType.document_ir, label="test doc")
        data = ref.model_dump()
        restored = ResourceRef(**data)
        assert restored.id == 42
        assert restored.resource_type == ResourceType.document_ir
        assert restored.label == "test doc"

    def test_resource_object_with_refs(self):
        """ResourceObject can hold references to other resources."""
        obj = ResourceObject(
            id=1,
            resource_type=ResourceType.workflow_node,
            content={"node_type": "task", "config": {}},
            refs=[ResourceRef(id=100, resource_type=ResourceType.prompt)],
            metadata=ResourceMetadata(owner_id=1, tags=["test"]),
        )
        data = obj.model_dump()
        assert data["resource_type"] == "workflow_node"
        assert len(data["refs"]) == 1

    @pytest.mark.asyncio
    async def test_resource_types_endpoint(self):
        """The resource type catalog endpoint returns all types."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _login(client)
            resp = await client.get(
                "/api/workflow/resource-types",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            returned_types = set(data["data"]["types"])
            for t in ResourceType:
                assert t.value in returned_types, f"Missing type: {t.value}"


# ── Workflow Definition Tests ──────────────────────────────────────


@pytest.mark.usefixtures("_cleanup_workflow_tables")
class TestWorkflowDefinition:
    @pytest.mark.asyncio
    async def test_create_and_list_definitions(self):
        """Can create a workflow definition and list it."""
        async with AsyncSessionLocal() as db:
            wd = WorkflowDefinition(
                name="test-workflow",
                owner_id=1,
                status="published",
                nodes=[{"id": "n1", "type": "task", "label": "Step 1"}],
                edges=[{"source": "n1", "target": "n2"}],
                version="1.0",
            )
            db.add(wd)
            await db.commit()
            wd_id = wd.id

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                token = await _login(client)
                resp = await client.get(
                    f"/api/workflow/definitions/{wd_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["data"]["name"] == "test-workflow"
                assert data["data"]["node_count"] == 1

    @pytest.mark.asyncio
    async def test_list_definitions_filtered(self):
        async with AsyncSessionLocal() as db:
            for name in ("wf-a", "wf-b", "wf-c"):
                db.add(WorkflowDefinition(name=name, owner_id=1, status="draft"))
            await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _login(client)
            resp = await client.get(
                "/api/workflow/definitions?status=draft",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["total"] >= 3


# ── Workflow Run Ledger Tests ──────────────────────────────────────


@pytest.mark.usefixtures("_cleanup_workflow_tables")
class TestWorkflowRunLedger:
    @pytest.mark.asyncio
    async def test_create_run_and_query(self):
        """Full lifecycle: create definition -> create run -> query."""
        async with AsyncSessionLocal() as db:
            wd = WorkflowDefinition(name="ledger-test", owner_id=1)
            db.add(wd)
            await db.commit()
            def_id = wd.id

            run = WorkflowRunRecord(
                definition_id=def_id,
                owner_id=1,
                trace="test-trace-001",
                context={"input": "hello"},
            )
            db.add(run)
            await db.commit()
            run_id = run.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _login(client)

            resp = await client.get(
                f"/api/workflow/runs/{run_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["trace"] == "test-trace-001"
            assert data["status"] == "pending"

            resp2 = await client.get(
                "/api/workflow/runs",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp2.json()["success"] is True
            assert resp2.json()["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_run_status_transitions(self):
        """Run status transitions through orchestrator service."""
        from app.services.workflow_orchestrator import (
            create_run, start_run, complete_run, get_run,
        )

        async with AsyncSessionLocal() as db:
            wd = WorkflowDefinition(name="transition-test", owner_id=1)
            db.add(wd)
            await db.commit()
            def_id = wd.id

            run = await create_run(db, definition_id=def_id, owner_id=1, trace="transition-001")
            assert run.status == "pending"
            run_id = run.id

            run = await start_run(db, run_id)
            assert run.status == "running"
            assert run.started_at is not None

            run = await complete_run(db, run_id)
            assert run.status == "completed"
            assert run.completed_at is not None

            run = await get_run(db, run_id)
            assert run is not None
            assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_step_lifecycle(self):
        """Step records can be created and linked to a run."""
        from app.services.workflow_orchestrator import (
            create_run, create_step, start_step, complete_step, list_steps,
        )
        from app.schemas.platform_resource import ResourceRef, ResourceType

        async with AsyncSessionLocal() as db:
            wd = WorkflowDefinition(name="step-lifecycle", owner_id=1)
            db.add(wd)
            await db.commit()
            def_id = wd.id

            run = await create_run(db, definition_id=def_id, owner_id=1)
            run_id = run.id

            input_refs = [ResourceRef(id=1, resource_type=ResourceType.document_ir, label="input doc")]
            step = await create_step(db, run_id=run_id, node_id="n1", node_type="task", input_ref=input_refs)
            assert step.status == "pending"
            step_id = step.id

            step = await start_step(db, step_id)
            assert step.status == "running"

            output_refs = [ResourceRef(id=2, resource_type=ResourceType.artifact, label="output artifact")]
            step = await complete_step(db, step_id, output_ref=output_refs, error=None)
            assert step.status == "completed"

            steps = await list_steps(db, run_id)
            assert len(steps) == 1
            assert steps[0].id == step_id

    @pytest.mark.asyncio
    async def test_run_with_steps_api(self):
        """Run steps can be queried via API."""
        async with AsyncSessionLocal() as db:
            wd = WorkflowDefinition(name="api-steps", owner_id=1)
            db.add(wd)
            await db.commit()
            run = WorkflowRunRecord(definition_id=wd.id, owner_id=1, status="running")
            db.add(run)
            await db.commit()
            run_id = run.id

            for i in range(3):
                step = WorkflowStepRecord(
                    run_id=run_id, node_id=f"n{i}", node_type="task", status="completed",
                )
                db.add(step)
            await db.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            token = await _login(client)
            resp = await client.get(
                f"/api/workflow/runs/{run_id}/steps",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            assert data["success"] is True
            assert data["data"]["total"] == 3

    @pytest.mark.asyncio
    async def test_failed_run(self):
        """A failed run has error populated."""
        from app.services.workflow_orchestrator import create_run, complete_run

        async with AsyncSessionLocal() as db:
            wd = WorkflowDefinition(name="fail-test", owner_id=1)
            db.add(wd)
            await db.commit()
            run = await create_run(db, definition_id=wd.id, owner_id=1)
            run = await complete_run(db, run.id, error="Step n1 failed: timeout")
            assert run.status == "failed"
            assert "timeout" in run.error
