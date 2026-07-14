from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..engine.engine import chat_with_degradation_chain
from ..services.capability_catalog import normalize_json_schema, parameter_schema
from .action_plan import ActionPlan, ActionPlanItem, ResourceRefType

ModelCall = Callable[..., Awaitable[dict]]

logger = logging.getLogger("v2.agent").getChild("runtime.action_planner")


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    capability: str = Field(pattern=r"^[A-Za-z0-9_-]+__[A-Za-z0-9_-]+$")
    arguments: dict
    depends_on: list[str]
    expected_references: list[ResourceRefType] = Field(default_factory=list)
    completion_check: str = Field(min_length=1, max_length=1000)
    approval_reason: str = Field(default="", max_length=1000)


class PlannerDecisionType(StrEnum):
    DIRECT_ANSWER = "direct_answer"
    NEED_USER_INPUT = "need_user_input"
    ACTION_GRAPH = "action_graph"


class PlannedActionGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PlannerDecisionType
    goal: str = Field(min_length=1, max_length=2000)
    answer: str = Field(default="", max_length=12000)
    actions: list[PlannedAction] = Field(default_factory=list, max_length=64)
    final_completion_check: str = Field(min_length=1, max_length=2000)
    need_user_input: list[str] = Field(default_factory=list, max_length=20)


class ActionPlanningResult(BaseModel):
    decision: PlannerDecisionType
    answer: str = ""
    plan: ActionPlan | None = None
    need_user_input: list[str] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)


class ActionPlannerError(RuntimeError):
    pass


def _catalog_candidates(catalog: dict) -> dict[str, dict]:
    raw_candidates = catalog.get("candidates", catalog.get("capabilities", []))
    return {
        f"{item.get('module')}__{item.get('action')}": item
        for item in raw_candidates
        if isinstance(item, dict) and item.get("module") and item.get("action")
    }


def _planner_schema(capability_names: list[str]) -> dict:
    schema = PlannedActionGraph.model_json_schema()
    planned_action = (schema.get("$defs") or {}).get("PlannedAction")
    if isinstance(planned_action, dict):
        properties = planned_action.get("properties")
        if isinstance(properties, dict) and isinstance(properties.get("capability"), dict):
            properties["capability"]["enum"] = capability_names
    return schema


def _planning_catalog(candidates: dict[str, dict]) -> list[dict]:
    return [
        {
            "capability": name,
            "brief": item.get("brief") or item.get("description") or name,
            "description": item.get("description") or "",
            "parameters": parameter_schema(item.get("parameters") or {}),
            "execution_contract": normalize_json_schema(item.get("execution_contract") or {}),
            "retrieval": item.get("retrieval") or {},
        }
        for name, item in candidates.items()
    ]


class ActionPlanner:
    def __init__(
        self,
        *,
        profile_key: str,
        model_call: ModelCall = chat_with_degradation_chain,
        max_planning_rounds: int = 3,
    ) -> None:
        self.profile_key = profile_key
        self.model_call = model_call
        self.max_planning_rounds = max(1, min(int(max_planning_rounds), 10))

    async def decide(
        self,
        *,
        goal: str,
        catalog: dict,
        messages: list[dict] | None = None,
        observations: dict[str, Any] | None = None,
        planning_round: int = 1,
        conversation_id: int | None = None,
    ) -> ActionPlanningResult:
        if planning_round < 1 or planning_round > self.max_planning_rounds:
            raise ActionPlannerError("planning_round_limit_exceeded")

        candidates = _catalog_candidates(catalog)
        catalog_hash = str(catalog.get("catalog_hash") or "")
        principal_version = str((catalog.get("principal") or {}).get("profile_version") or "")
        logger.info(
            "Planner start: conv=%s round=%d goal=%s candidates=%d low_confidence=%s top=%s",
            conversation_id,
            planning_round,
            goal[:120],
            len(candidates),
            bool(catalog.get("low_confidence")),
            [name for name in list(candidates)[:8]],
        )
        if not catalog_hash or not principal_version:
            raise ActionPlannerError("catalog_security_binding_is_missing")

        observation_payload = {
            str(action_id): (
                value.model_dump(mode="json", by_alias=True)
                if hasattr(value, "model_dump")
                else value
            )
            for action_id, value in (observations or {}).items()
        }
        planner_schema = _planner_schema(list(candidates))
        planning_context = {
            "goal": goal,
            "planning_round": planning_round,
            "authorized_capabilities": _planning_catalog(candidates),
            "previous_observations": observation_payload,
            "rules": [
                "Only use capabilities listed in authorized_capabilities.",
                "Choose direct_answer only when the request can be answered without current or capability-provided evidence.",
                "Choose need_user_input only when required information is missing and no authorized capability can obtain it.",
                "Choose action_graph when an authorized capability is needed to obtain evidence or perform work.",
                "Use depends_on for every data dependency.",
                "Use ${action_id.references[index].id} or .locator for prior outputs.",
                "Do not repeat a failed action; produce a revised plan or request user input.",
            ],
            "output_contract": {
                "format": "Return exactly one JSON object that validates against schema. Do not use Markdown or add prose.",
                "schema": planner_schema,
            },
        }
        model_messages = list(messages or [])
        model_messages.append({
            "role": "user",
            "content": json.dumps(planning_context, ensure_ascii=False, default=str),
        })
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "agent_action_plan",
                "strict": False,
                "schema": planner_schema,
            },
        }
        result = await self.model_call(
            messages=model_messages,
            profile_key=self.profile_key,
            tools=None,
            conversation_id=conversation_id,
            response_format=response_format,
        )
        if result.get("error"):
            raise ActionPlannerError(str(result["error"]))

        raw_content = result.get("content")
        try:
            payload = raw_content if isinstance(raw_content, dict) else json.loads(str(raw_content or ""))
            planned = PlannedActionGraph.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ActionPlannerError("invalid_structured_action_plan") from exc

        if planned.decision == PlannerDecisionType.DIRECT_ANSWER:
            if not planned.answer.strip() or planned.actions or planned.need_user_input:
                raise ActionPlannerError("invalid_direct_answer_decision")
            logger.info(
                "Planner decision: conv=%s round=%d decision=direct_answer answer_chars=%d",
                conversation_id,
                planning_round,
                len(planned.answer),
            )
            return ActionPlanningResult(
                decision=planned.decision,
                answer=planned.answer.strip(),
                usage=result.get("usage") or {},
            )
        if planned.decision == PlannerDecisionType.NEED_USER_INPUT:
            if not planned.need_user_input or planned.actions:
                raise ActionPlannerError("invalid_need_user_input_decision")
            logger.info(
                "Planner decision: conv=%s round=%d decision=need_user_input questions=%d",
                conversation_id,
                planning_round,
                len(planned.need_user_input),
            )
            return ActionPlanningResult(
                decision=planned.decision,
                answer=planned.answer.strip(),
                need_user_input=planned.need_user_input,
                usage=result.get("usage") or {},
            )
        if not planned.actions or planned.answer.strip() or planned.need_user_input:
            raise ActionPlannerError("invalid_action_graph_decision")

        actions: list[ActionPlanItem] = []
        for item in planned.actions:
            candidate = candidates.get(item.capability)
            if candidate is None:
                raise ActionPlannerError(f"capability_not_in_catalog:{item.capability}")
            capability_id = int(candidate.get("capability_id") or 0)
            if capability_id <= 0:
                raise ActionPlannerError(f"capability_identity_is_missing:{item.capability}")
            actions.append(ActionPlanItem(
                id=item.id,
                capability_id=capability_id,
                capability=item.capability,
                arguments=item.arguments,
                depends_on=item.depends_on,
                expected_references=item.expected_references,
                completion_check=item.completion_check,
                approval_reason=item.approval_reason,
            ))

        try:
            plan = ActionPlan(
                goal=planned.goal,
                catalog_hash=catalog_hash,
                principal_version=principal_version,
                actions=actions,
                final_completion_check=planned.final_completion_check,
                need_user_input=planned.need_user_input,
            )
        except ValidationError as exc:
            raise ActionPlannerError("invalid_structured_action_plan") from exc
        logger.info(
            "Planner decision: conv=%s round=%d decision=action_graph actions=%s",
            conversation_id,
            planning_round,
            [item.capability for item in plan.actions],
        )
        return ActionPlanningResult(
            decision=planned.decision,
            plan=plan,
            usage=result.get("usage") or {},
        )

    async def plan(
        self,
        *,
        goal: str,
        catalog: dict,
        messages: list[dict] | None = None,
        observations: dict[str, Any] | None = None,
        planning_round: int = 1,
        conversation_id: int | None = None,
    ) -> ActionPlan:
        result = await self.decide(
            goal=goal,
            catalog=catalog,
            messages=messages,
            observations=observations,
            planning_round=planning_round,
            conversation_id=conversation_id,
        )
        if result.plan is None:
            raise ActionPlannerError(f"planner_decision_has_no_action_graph:{result.decision}")
        return result.plan
