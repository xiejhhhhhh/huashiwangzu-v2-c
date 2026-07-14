from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from .action_graph_executor import ActionGraphExecutor, ActionGraphStatus
from .action_plan import ActionObservation, ActionPlanCheckpoint, ActionPlanItem, ActionState
from .action_plan_validator import ActionPlanValidationError, ActionPlanValidator
from .action_planner import ActionPlanner, ActionPlannerError, PlannerDecisionType

ExecuteAction = Callable[[ActionPlanItem, dict, dict], Awaitable[object]]
RefreshCatalog = Callable[[], Awaitable[dict]]
PlanCallback = Callable[[ActionPlanCheckpoint], Awaitable[None]]
PlanningCallback = Callable[[int], Awaitable[None]]
ObservationCallback = Callable[
    [ActionPlanCheckpoint, ActionPlanItem, ActionObservation, object | None],
    Awaitable[None],
]

logger = logging.getLogger("v2.agent").getChild("runtime.action")


class ActionRuntimeStatus(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    NEED_USER_INPUT = "need_user_input"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ActionRuntimeResult:
    status: ActionRuntimeStatus
    answer: str = ""
    need_user_input: list[str] = field(default_factory=list)
    checkpoint: ActionPlanCheckpoint | None = None
    planning_rounds: int = 0
    usage: dict = field(default_factory=dict)
    failure_reason: str = ""


class StructuredActionRuntime:
    """The one Planner -> Validator -> ActionGraphExecutor runtime.

    Conversation and subagent adapters provide transport/persistence callbacks;
    neither adapter owns a second model/tool loop.
    """

    def __init__(
        self,
        *,
        owner_id: int,
        profile_key: str,
        catalog: dict,
        execute_action: ExecuteAction,
        max_planning_rounds: int = 3,
        max_concurrency: int = 8,
        planner: ActionPlanner | None = None,
        refresh_catalog: RefreshCatalog | None = None,
        on_plan: PlanCallback | None = None,
        on_planning: PlanningCallback | None = None,
        on_observation: ObservationCallback | None = None,
    ) -> None:
        self.owner_id = int(owner_id)
        self.profile_key = profile_key
        self.catalog = catalog
        self.execute_action = execute_action
        self.max_planning_rounds = max(1, min(int(max_planning_rounds), 10))
        self.max_concurrency = max(1, int(max_concurrency))
        self.planner = planner or ActionPlanner(
            profile_key=profile_key,
            max_planning_rounds=self.max_planning_rounds,
        )
        self.refresh_catalog = refresh_catalog
        self.on_plan = on_plan
        self.on_planning = on_planning
        self.on_observation = on_observation

    async def run(
        self,
        *,
        goal: str,
        messages: list[dict] | None = None,
        checkpoint: ActionPlanCheckpoint | None = None,
        conversation_id: int | None = None,
    ) -> ActionRuntimeResult:
        usage: dict = {}
        completed: dict[str, tuple[ActionPlanItem, ActionObservation]] = {}
        prior_observations: dict[str, dict] = {}
        next_round = 1

        if checkpoint is not None:
            next_round = checkpoint.planning_round
            self._remember_checkpoint(checkpoint, completed, prior_observations)
            if self._catalog_is_stale(checkpoint):
                prior_observations["resume"] = {
                    "state": "failed",
                    "error_class": "stale_catalog",
                    "error": "能力目录已变化，需要重新规划。",
                }
                if self.refresh_catalog is not None:
                    self.catalog = await self.refresh_catalog()
                next_round += 1
            elif not self._requires_replan(checkpoint):
                resumed = await self._execute(checkpoint)
                if resumed.status == ActionGraphStatus.COMPLETED:
                    return ActionRuntimeResult(
                        status=ActionRuntimeStatus.COMPLETED,
                        checkpoint=checkpoint,
                        planning_rounds=next_round,
                    )
                if resumed.status == ActionGraphStatus.BLOCKED:
                    return ActionRuntimeResult(
                        status=ActionRuntimeStatus.BLOCKED,
                        checkpoint=checkpoint,
                        planning_rounds=next_round,
                        failure_reason=resumed.reason,
                    )
                self._remember_checkpoint(checkpoint, completed, prior_observations)
                next_round += 1

        for planning_round in range(next_round, self.max_planning_rounds + 1):
            if self.on_planning is not None:
                await self.on_planning(planning_round)
            try:
                decision = await self.planner.decide(
                    goal=goal,
                    catalog=self.catalog,
                    messages=messages,
                    observations=prior_observations,
                    planning_round=planning_round,
                    conversation_id=conversation_id,
                )
            except ActionPlannerError as exc:
                logger.warning(
                    "Planner error in round %d: %s",
                    planning_round,
                    exc,
                )
                prior_observations[f"plan:{planning_round}"] = {
                    "state": "failed",
                    "error_class": str(exc),
                    "error": f"规划器返回格式异常（{exc}），尝试重新规划。",
                }
                continue
            _merge_usage(usage, decision.usage)
            logger.info(
                "Structured runtime decision: conv=%s round=%d decision=%s candidate_count=%d",
                conversation_id,
                planning_round,
                decision.decision,
                len(self.catalog.get("candidates") or []),
            )
            if decision.decision == PlannerDecisionType.DIRECT_ANSWER:
                return ActionRuntimeResult(
                    status=ActionRuntimeStatus.DIRECT_ANSWER,
                    answer=decision.answer,
                    planning_rounds=planning_round,
                    usage=usage,
                )
            if decision.decision == PlannerDecisionType.NEED_USER_INPUT:
                return ActionRuntimeResult(
                    status=ActionRuntimeStatus.NEED_USER_INPUT,
                    answer=decision.answer,
                    need_user_input=decision.need_user_input,
                    planning_rounds=planning_round,
                    usage=usage,
                )
            if decision.plan is None:
                raise ActionPlannerError("action_graph_decision_is_missing_plan")

            validator = ActionPlanValidator(user_id=self.owner_id, catalog=self.catalog)
            try:
                validator.validate_plan(decision.plan)
            except ActionPlanValidationError as exc:
                logger.warning(
                    "Action plan validation failed: conv=%s round=%d issues=%s",
                    conversation_id,
                    planning_round,
                    [item.code for item in exc.issues],
                )
                prior_observations[f"plan:{planning_round}"] = {
                    "state": "failed",
                    "error_class": "action_plan_invalid",
                    "issues": [
                        {"action_id": item.action_id, "code": item.code, "message": item.message}
                        for item in exc.issues
                    ],
                }
                continue

            checkpoint = ActionPlanCheckpoint(
                plan=decision.plan,
                planning_round=planning_round,
            )
            self._seed_completed(checkpoint, completed)
            if self.on_plan is not None:
                await self.on_plan(checkpoint)

            execution = await self._execute(checkpoint, validator=validator)
            if execution.status == ActionGraphStatus.COMPLETED:
                return ActionRuntimeResult(
                    status=ActionRuntimeStatus.COMPLETED,
                    checkpoint=checkpoint,
                    planning_rounds=planning_round,
                    usage=usage,
                )
            if execution.status == ActionGraphStatus.BLOCKED:
                return ActionRuntimeResult(
                    status=ActionRuntimeStatus.BLOCKED,
                    checkpoint=checkpoint,
                    planning_rounds=planning_round,
                    usage=usage,
                    failure_reason=execution.reason,
                )

            self._remember_checkpoint(checkpoint, completed, prior_observations)
            if self.refresh_catalog is not None and self._has_stale_failure(checkpoint):
                self.catalog = await self.refresh_catalog()

        return ActionRuntimeResult(
            status=ActionRuntimeStatus.FAILED,
            checkpoint=checkpoint,
            planning_rounds=self.max_planning_rounds,
            usage=usage,
            failure_reason="planning_round_limit_exceeded",
        )

    async def _execute(
        self,
        checkpoint: ActionPlanCheckpoint,
        *,
        validator: ActionPlanValidator | None = None,
    ):
        actions = {item.id: item for item in checkpoint.plan.actions}
        raw_results: dict[str, object] = {}

        async def execute(action: ActionPlanItem, arguments: dict, contract: dict) -> object:
            result = await self.execute_action(action, arguments, contract)
            raw_results[action.id] = result
            return result

        async def observe(state: ActionPlanCheckpoint, observation: ActionObservation) -> None:
            if self.on_observation is None:
                return
            action = actions[observation.action_id]
            await self.on_observation(
                state,
                action,
                observation,
                raw_results.get(observation.action_id),
            )

        return await ActionGraphExecutor(
            catalog=self.catalog,
            execute_callback=execute,
            validator=validator or ActionPlanValidator(user_id=self.owner_id, catalog=self.catalog),
            observation_callback=observe,
            max_concurrency=self.max_concurrency,
        ).execute(checkpoint)

    def _catalog_is_stale(self, checkpoint: ActionPlanCheckpoint) -> bool:
        plan_hash = str(checkpoint.plan.catalog_hash or "")
        current_hash = str(self.catalog.get("catalog_hash") or "")
        return bool(plan_hash and current_hash and plan_hash != current_hash)

    @staticmethod
    def _requires_replan(checkpoint: ActionPlanCheckpoint) -> bool:
        return any(
            observation.state in {ActionState.FAILED, ActionState.BLOCKED, ActionState.CANCELLED}
            for observation in checkpoint.observations.values()
        )

    @staticmethod
    def _has_stale_failure(checkpoint: ActionPlanCheckpoint) -> bool:
        return any(
            observation.error_class in {
                "stale_catalog",
                "capability_catalog_stale",
                "stale_principal",
                "capability_not_authorized",
            }
            for observation in checkpoint.observations.values()
        )

    @staticmethod
    def _remember_checkpoint(
        checkpoint: ActionPlanCheckpoint,
        completed: dict[str, tuple[ActionPlanItem, ActionObservation]],
        prior_observations: dict[str, dict],
    ) -> None:
        actions = {item.id: item for item in checkpoint.plan.actions}
        for action_id, observation in checkpoint.observations.items():
            action = actions.get(action_id)
            if action is None:
                continue
            prior_observations[f"round_{checkpoint.planning_round}:{action_id}"] = {
                "action": action.model_dump(mode="json", by_alias=True),
                "observation": observation.model_dump(mode="json", by_alias=True),
            }
            if observation.state == ActionState.COMPLETED:
                completed[action_id] = (action, observation)

    @staticmethod
    def _seed_completed(
        checkpoint: ActionPlanCheckpoint,
        completed: dict[str, tuple[ActionPlanItem, ActionObservation]],
    ) -> None:
        for action in checkpoint.plan.actions:
            prior = completed.get(action.id)
            if prior is None:
                continue
            prior_action, observation = prior
            if (
                prior_action.capability_id == action.capability_id
                and prior_action.capability == action.capability
                and _canonical_json(prior_action.arguments) == _canonical_json(action.arguments)
            ):
                checkpoint.observations[action.id] = observation.model_copy(deep=True)


def _merge_usage(target: dict, source: dict | None) -> None:
    if not isinstance(source, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = source.get(key)
        if isinstance(value, (int, float)):
            target[key] = int(target.get(key, 0) or 0) + int(value)
    target["model_call_count"] = int(target.get("model_call_count", 0) or 0) + 1


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
