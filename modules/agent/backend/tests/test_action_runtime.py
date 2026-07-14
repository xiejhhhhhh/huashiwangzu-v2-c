from __future__ import annotations

import pytest

from modules.agent.backend.runtime import action_plan_validator
from modules.agent.backend.runtime.action_plan import ActionPlan, ActionPlanCheckpoint
from modules.agent.backend.runtime.action_planner import (
    ActionPlanningResult,
    PlannerDecisionType,
)
from modules.agent.backend.runtime.action_runtime import (
    ActionRuntimeStatus,
    StructuredActionRuntime,
)


def _catalog() -> dict:
    return {
        "catalog_hash": "a" * 64,
        "principal": {"profile_version": "b" * 16},
        "candidates": [
            {
                "capability_id": 1,
                "module": "demo",
                "action": "read",
                "parameters": {},
                "execution_contract": {"side_effect_level": "none"},
            },
            {
                "capability_id": 2,
                "module": "demo",
                "action": "fail",
                "parameters": {},
                "execution_contract": {"side_effect_level": "none"},
            },
            {
                "capability_id": 3,
                "module": "demo",
                "action": "recover",
                "parameters": {},
                "execution_contract": {"side_effect_level": "none"},
            },
        ],
    }


def _plan(round_number: int) -> ActionPlan:
    if round_number == 1:
        actions = [
            {
                "id": "read",
                "capability_id": 1,
                "capability": "demo__read",
                "completion_check": "Read completes",
            },
            {
                "id": "fail",
                "capability_id": 2,
                "capability": "demo__fail",
                "completion_check": "Failure is observed",
            },
        ]
    else:
        actions = [
            {
                "id": "read",
                "capability_id": 1,
                "capability": "demo__read",
                "completion_check": "Read remains complete",
            },
            {
                "id": "recover",
                "capability_id": 3,
                "capability": "demo__recover",
                "depends_on": ["read"],
                "completion_check": "Recovery completes",
            },
        ]
    return ActionPlan.model_validate({
        "goal": "Complete after a recoverable failure",
        "catalog_hash": "a" * 64,
        "principal_version": "b" * 16,
        "actions": actions,
        "final_completion_check": "All required work completes",
    })


class _SequencePlanner:
    def __init__(self) -> None:
        self.observations: list[dict] = []

    async def decide(self, **kwargs: object) -> ActionPlanningResult:
        self.observations.append(dict(kwargs.get("observations") or {}))
        round_number = int(kwargs["planning_round"])
        return ActionPlanningResult(
            decision=PlannerDecisionType.ACTION_GRAPH,
            plan=_plan(round_number),
        )


async def _allow_snapshot(**kwargs: object) -> dict:
    return {}


@pytest.mark.asyncio
async def test_runtime_replans_explicitly_and_preserves_completed_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(action_plan_validator, "validate_execution_snapshot", _allow_snapshot)
    calls: list[str] = []

    async def execute(action, arguments, contract):
        calls.append(action.id)
        if action.id == "fail":
            return {"success": False, "error": "temporary failure"}
        return {"success": True}

    planner = _SequencePlanner()
    result = await StructuredActionRuntime(
        owner_id=1,
        profile_key="demo",
        catalog=_catalog(),
        execute_action=execute,
        max_planning_rounds=2,
        planner=planner,  # type: ignore[arg-type]
    ).run(goal="complete the task")

    assert result.status == ActionRuntimeStatus.COMPLETED
    assert result.planning_rounds == 2
    assert calls == ["read", "fail", "recover"]
    assert "round_1:fail" in planner.observations[1]


@pytest.mark.asyncio
async def test_runtime_notifies_before_each_planning_round() -> None:
    events: list[tuple[str, int]] = []

    class Planner:
        async def decide(self, **kwargs: object) -> ActionPlanningResult:
            round_number = int(kwargs["planning_round"])
            events.append(("decide", round_number))
            return ActionPlanningResult(
                decision=PlannerDecisionType.DIRECT_ANSWER,
                answer="已完成规划。",
            )

    async def on_planning(round_number: int) -> None:
        events.append(("planning", round_number))

    async def execute(action, arguments, contract):
        raise AssertionError("executor must not run for a direct answer")

    result = await StructuredActionRuntime(
        owner_id=1,
        profile_key="demo",
        catalog=_catalog(),
        execute_action=execute,
        planner=Planner(),  # type: ignore[arg-type]
        on_planning=on_planning,
    ).run(goal="hello")

    assert result.status == ActionRuntimeStatus.DIRECT_ANSWER
    assert events == [("planning", 1), ("decide", 1)]


@pytest.mark.asyncio
async def test_runtime_returns_direct_answer_without_executor() -> None:
    class Planner:
        async def decide(self, **kwargs: object) -> ActionPlanningResult:
            return ActionPlanningResult(
                decision=PlannerDecisionType.DIRECT_ANSWER,
                answer="No action is needed.",
            )

    async def execute(action, arguments, contract):
        raise AssertionError("executor must not run for a direct answer")

    result = await StructuredActionRuntime(
        owner_id=1,
        profile_key="demo",
        catalog=_catalog(),
        execute_action=execute,
        planner=Planner(),  # type: ignore[arg-type]
    ).run(goal="hello")

    assert result.status == ActionRuntimeStatus.DIRECT_ANSWER
    assert result.answer == "No action is needed."


@pytest.mark.asyncio
async def test_runtime_refreshes_catalog_before_replan_on_stale_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validations = 0
    refreshes = 0

    async def validate_snapshot(**kwargs: object) -> dict:
        nonlocal validations
        validations += 1
        if validations == 1:
            raise RuntimeError("capability_catalog_stale")
        return {}

    async def refresh_catalog() -> dict:
        nonlocal refreshes
        refreshes += 1
        return _catalog()

    async def execute(action, arguments, contract):
        return {"success": True}

    monkeypatch.setattr(action_plan_validator, "validate_execution_snapshot", validate_snapshot)
    result = await StructuredActionRuntime(
        owner_id=1,
        profile_key="demo",
        catalog=_catalog(),
        execute_action=execute,
        max_planning_rounds=2,
        planner=_SequencePlanner(),  # type: ignore[arg-type]
        refresh_catalog=refresh_catalog,
    ).run(goal="complete the task")

    assert result.status == ActionRuntimeStatus.COMPLETED
    assert result.planning_rounds == 2
    assert refreshes == 1


@pytest.mark.asyncio
async def test_runtime_replans_when_resumed_catalog_hash_changes() -> None:
    old_catalog = _catalog()
    current_catalog = {**old_catalog, "catalog_hash": "c" * 64}
    checkpoint = ActionPlanCheckpoint(
        plan=_plan(1),
        planning_round=1,
    )
    decisions: list[int] = []
    calls: list[str] = []

    class Planner:
        async def decide(self, **kwargs: object) -> ActionPlanningResult:
            round_number = int(kwargs["planning_round"])
            decisions.append(round_number)
            return ActionPlanningResult(
                decision=PlannerDecisionType.DIRECT_ANSWER,
                answer="已按新能力目录重新规划。",
            )

    async def execute(action, arguments, contract):
        calls.append(action.id)
        return {"success": True}

    async def refresh_catalog() -> dict:
        return current_catalog

    result = await StructuredActionRuntime(
        owner_id=1,
        profile_key="demo",
        catalog=current_catalog,
        execute_action=execute,
        max_planning_rounds=2,
        planner=Planner(),  # type: ignore[arg-type]
        refresh_catalog=refresh_catalog,
    ).run(goal="resume with changed catalog", checkpoint=checkpoint)

    assert result.status == ActionRuntimeStatus.DIRECT_ANSWER
    assert result.answer == "已按新能力目录重新规划。"
    assert decisions == [2]
    assert calls == []
