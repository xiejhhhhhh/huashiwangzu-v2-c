"""Runtime bridge between live Agent execution and the workflow ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .._utils import artifact_refs_from_value
from ..services import workflow_service as workflow_svc
from ..services.action_policy import _sanitize_tool_arg_value, classify_side_effect_level
from ..services.tool_discovery import parse_tool_name


def _truncate(value: str, limit: int = 240) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[:limit - 3] + "..."


def _safe_ref(value: object) -> dict:
    ref = {
        "storage": "sanitized_summary",
        "summary": _sanitize_tool_arg_value(value if value is not None else {}),
    }
    artifact_refs = artifact_refs_from_value(value)
    if artifact_refs:
        ref["artifact_refs"] = artifact_refs
    return ref


def _tool_args(tool: dict) -> dict:
    args = tool.get("args") or tool.get("arguments") or {}
    if isinstance(args, str):
        try:
            parsed = json.loads(args) if args.strip() else {}
        except (json.JSONDecodeError, TypeError):
            return {"raw": _truncate(args)}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return args if isinstance(args, dict) else {"value": args}


def _effective_tool_name(tool: dict) -> str:
    name = str(tool.get("name") or "")
    args = _tool_args(tool)
    if name == "skill_use":
        inner = str(args.get("name") or "").strip()
        if inner:
            return inner
    return name


def _target_for_tool(tool_name: str) -> tuple[str | None, str | None]:
    if "__" not in tool_name:
        return None, None
    try:
        return parse_tool_name(tool_name)
    except Exception:
        module_key, action = tool_name.split("__", 1)
        return module_key, action


def _result_failed(result: object) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("policy_action") in {"block", "deny"}:
        return True
    if result.get("approval_required"):
        return False
    if result.get("error") or result.get("denied") or result.get("policy_blocked"):
        return True
    if result.get("success") is False:
        return True
    inner = result.get("data", result)
    return isinstance(inner, dict) and (inner.get("success") is False or bool(inner.get("error")))


def _status_for_result(result_event: dict) -> str:
    result = result_event.get("result", {})
    if isinstance(result, dict) and result.get("approval_required"):
        return "waiting_approval"
    if result_event.get("status") == "failed" or _result_failed(result):
        return "failed"
    return "completed"


def _error_signature(result_event: dict) -> str | None:
    result = result_event.get("result", {})
    if not isinstance(result, dict):
        return None
    message = result.get("error") or result.get("message") or result_event.get("error_class")
    inner = result.get("data")
    if not message and isinstance(inner, dict):
        message = inner.get("error") or inner.get("message")
    return _truncate(str(message), 256) if message else None


def _artifact_refs_from_tool_events(tool_events: list[dict]) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()
    for event in tool_events:
        if event.get("type") != "tool_result":
            continue
        for ref in artifact_refs_from_value(event.get("result", {})):
            key = f"{ref.get('type')}:{ref.get('ref_key')}:{ref.get('ref_id')}"
            if key in seen:
                continue
            seen.add(key)
            refs.append({
                **ref,
                "tool_name": event.get("effective_tool_name") or event.get("name") or "",
                "tool_call_id": event.get("tool_call_id") or "",
            })
    return refs


def should_open_workflow_from_preflight(preflight: dict | None) -> bool:
    if not isinstance(preflight, dict) or preflight.get("error"):
        return False
    category = str(preflight.get("task_category") or "")
    if category in {"smalltalk", "creation"}:
        return False
    first_actions = list((preflight.get("tool_strategy") or {}).get("first_actions") or [])
    if first_actions == ["clarify"]:
        return False
    return any(action not in {"direct_answer", "answer_with_caveat", "clarify"} for action in first_actions)


@dataclass
class WorkflowRuntimeLink:
    """Mutable workflow context for one live Agent turn."""

    conversation_id: int
    owner_id: int
    user_input: str
    profile_key: str = "deepseek-v4-flash"
    user_message_id: int | None = None
    intent_preflight: dict | None = None
    agent_run_id: str = field(default_factory=lambda: f"agent-run-{uuid4().hex}")
    run_id: int | None = None
    step_id: int | None = None
    llm_to_ledger_call: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_channel_values(
        cls,
        *,
        conversation_id: int,
        owner_id: int,
        user_input: str,
        profile_key: str,
        channel_values: dict | None,
    ) -> "WorkflowRuntimeLink":
        workflow = (channel_values or {}).get("workflow") or {}
        return cls(
            conversation_id=conversation_id,
            owner_id=owner_id,
            user_input=user_input,
            profile_key=profile_key,
            user_message_id=workflow.get("user_message_id"),
            intent_preflight=workflow.get("intent_preflight"),
            agent_run_id=workflow.get("agent_run_id") or f"agent-run-{uuid4().hex}",
            run_id=workflow.get("run_id"),
            step_id=workflow.get("step_id"),
            llm_to_ledger_call={
                str(key): int(value)
                for key, value in (workflow.get("llm_to_ledger_call") or {}).items()
                if value is not None
            },
        )

    def to_channel_values(self) -> dict:
        return {
            "run_id": self.run_id,
            "step_id": self.step_id,
            "agent_run_id": self.agent_run_id,
            "user_message_id": self.user_message_id,
            "intent_preflight": self.intent_preflight,
            "llm_to_ledger_call": self.llm_to_ledger_call,
        }

    async def ensure_started(self, db: AsyncSession, *, reason: str = "tool_call") -> None:
        if self.run_id is None:
            run = await workflow_svc.create_workflow(
                db,
                title=_truncate(self.user_input, 80) or "Agent task",
                intent=self.user_input or "",
                source="agent_runtime",
                owner_id=self.owner_id,
                creator_id=self.owner_id,
                extra_meta={
                    "conversation_id": self.conversation_id,
                    "message_id": self.user_message_id,
                    "agent_run_id": self.agent_run_id,
                    "reason": reason,
                    "profile_key": self.profile_key,
                    "intent_preflight": self.intent_preflight or {},
                },
            )
            self.run_id = run.id
            await workflow_svc.start_workflow(db, run.id, progress_summary="Agent 正在处理")
        if self.step_id is None and self.run_id is not None:
            step = await workflow_svc.create_step(
                db,
                run_id=self.run_id,
                step_key=f"turn-{self.agent_run_id}",
                title="Agent runtime turn",
                step_type="agent",
                input_ref={
                    "conversation_id": self.conversation_id,
                    "message_id": self.user_message_id,
                    "summary": _truncate(self.user_input),
                },
                extra_meta={"agent_run_id": self.agent_run_id, "reason": reason},
            )
            self.step_id = step.id
            await workflow_svc.update_step_status(
                db,
                step.id,
                status="running",
                run_id=self.run_id,
                summary="Agent turn started",
            )

    async def record_tool_started(self, db: AsyncSession, tool: dict) -> int | None:
        await self.ensure_started(db, reason="tool_call")
        if self.run_id is None:
            return None
        llm_tool_call_id = str(tool.get("tool_call_id") or "")
        if llm_tool_call_id and llm_tool_call_id in self.llm_to_ledger_call:
            return self.llm_to_ledger_call[llm_tool_call_id]
        tool_name = _effective_tool_name(tool)
        target_module, action = _target_for_tool(tool_name)
        side_effect_level = classify_side_effect_level(tool_name)
        approval_policy = "requires_confirmation" if side_effect_level in {"outbound", "admin_config"} else "auto"
        call = await workflow_svc.record_tool_call(
            db,
            run_id=self.run_id,
            step_id=self.step_id,
            tool_name=tool_name,
            target_module=target_module,
            action=action,
            arguments=_tool_args(tool),
            caller=f"user:{self.owner_id}" if self.owner_id else "system:agent",
            side_effect_level=side_effect_level,
            approval_policy=approval_policy,
            status="running",
            agent_run_id=self.agent_run_id,
            extra_meta={
                "conversation_id": self.conversation_id,
                "llm_tool_call_id": llm_tool_call_id,
                "raw_tool_name": tool.get("name"),
            },
        )
        if llm_tool_call_id:
            self.llm_to_ledger_call[llm_tool_call_id] = call.id
        return call.id

    async def mark_invalid_tool(self, db: AsyncSession, tool: dict, message: str) -> None:
        call_id = await self.record_tool_started(db, tool)
        if not call_id:
            return
        await workflow_svc.update_tool_call_status(
            db,
            call_id,
            status="failed",
            result_ref={"summary": _truncate(message), "kind": "invalid_tool_name"},
            error_class="invalid_tool_name",
            error_signature=_truncate(message, 256),
        )
        if self.run_id:
            await workflow_svc.record_failure(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                tool_call_id=call_id,
                failure_type="tool_error",
                error_signature=_truncate(message, 256),
                retryable=True,
                next_action="retry",
                evidence_ref={"tool": tool.get("name"), "message": message},
            )

    async def mark_tool_result(self, db: AsyncSession, result_event: dict) -> None:
        llm_tool_call_id = str(result_event.get("tool_call_id") or "")
        call_id = self.llm_to_ledger_call.get(llm_tool_call_id)
        if not call_id:
            return
        status = _status_for_result(result_event)
        error_sig = _error_signature(result_event)
        await workflow_svc.update_tool_call_status(
            db,
            call_id,
            status=status,
            result_ref=_safe_ref(result_event.get("result", {})),
            error_class=result_event.get("error_class") if status == "failed" else None,
            error_signature=error_sig if status == "failed" else None,
        )
        if status == "failed" and self.run_id:
            await workflow_svc.record_failure(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                tool_call_id=call_id,
                failure_type="tool_error",
                error_signature=error_sig,
                retryable=not bool(result_event.get("hard_failure")),
                next_action="retry" if not result_event.get("hard_failure") else "manual",
                evidence_ref=_safe_ref(result_event),
            )
        artifact_refs = artifact_refs_from_value(result_event.get("result", {}))
        if artifact_refs and self.run_id:
            await workflow_svc.create_artifact(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                artifact_type="tool_reference",
                storage_kind="inline_json",
                storage_ref={
                    "tool_call_id": call_id,
                    "llm_tool_call_id": llm_tool_call_id,
                    "tool_name": result_event.get("effective_tool_name") or result_event.get("name") or "",
                    "refs": artifact_refs,
                },
                visibility="user",
                lifecycle="candidate",
                summary=f"{len(artifact_refs)} reference id(s) from tool result",
            )
        result_tool_name = str(
            result_event.get("effective_tool_name")
            or result_event.get("name")
            or ""
        )
        if result_tool_name == "agent__spawn_subagent":
            await self.record_subagent_result(db, result_event, parent_tool_call_id=call_id)

    async def record_subagent_result(
        self,
        db: AsyncSession,
        result_event: dict,
        *,
        parent_tool_call_id: int | None = None,
    ) -> None:
        if self.run_id is None:
            return
        result = result_event.get("result", {})
        payload = result.get("data", result) if isinstance(result, dict) else {}
        if not isinstance(payload, dict):
            return
        for index, item in enumerate(payload.get("results") or []):
            if not isinstance(item, dict):
                continue
            status = "completed" if item.get("status") == "completed" else "failed"
            step = await workflow_svc.create_step(
                db,
                run_id=self.run_id,
                step_key=f"subagent-{self.agent_run_id}-{index}",
                title=_truncate(str(item.get("task") or f"Subagent task {index + 1}"), 120),
                step_type="subagent",
                input_ref={"parent_tool_call_id": parent_tool_call_id},
                extra_meta={"parent_tool_call_id": parent_tool_call_id, "agent_run_id": self.agent_run_id},
            )
            await workflow_svc.update_step_status(
                db,
                step.id,
                status=status,
                run_id=self.run_id,
                summary=_truncate(str(item.get("conclusion") or item.get("error") or status)),
                output_ref=_safe_ref(item),
                error_class="subagent_error" if status == "failed" else None,
                error_signature=_truncate(str(item.get("error") or ""), 256) if status == "failed" else None,
            )
            if item.get("conclusion"):
                await workflow_svc.create_artifact(
                    db,
                    run_id=self.run_id,
                    step_id=step.id,
                    artifact_type="subagent_result",
                    storage_kind="inline_summary",
                    storage_ref=_safe_ref(item),
                    visibility="developer",
                    lifecycle="candidate",
                    summary=_truncate(str(item.get("conclusion")), 240),
                )
            if status == "failed":
                await workflow_svc.record_failure(
                    db,
                    run_id=self.run_id,
                    step_id=step.id,
                    tool_call_id=parent_tool_call_id,
                    failure_type="tool_error",
                    error_signature=_truncate(str(item.get("error") or "subagent failed"), 256),
                    retryable=False,
                    next_action="manual",
                    evidence_ref=_safe_ref(item),
                )

    async def record_turn_completion(
        self,
        db: AsyncSession,
        *,
        message_id: int | None,
        tool_events: list[dict],
        completion_evidence: list[dict] | None = None,
        usage: dict | None = None,
    ) -> None:
        if self.run_id is None:
            return
        if message_id:
            await workflow_svc.create_artifact(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                artifact_type="assistant_response",
                storage_kind="message_id",
                storage_ref={"conversation_id": self.conversation_id, "message_id": message_id},
                visibility="user",
                lifecycle="published",
                summary="Agent response",
                extra_meta={"usage": usage or {}},
            )
        if completion_evidence:
            await workflow_svc.create_artifact(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                artifact_type="completion_evidence",
                storage_kind="inline_json",
                storage_ref={"items": completion_evidence},
                visibility="developer",
                lifecycle="candidate",
                summary=f"{len(completion_evidence)} completion evidence item(s)",
            )
        artifact_refs = _artifact_refs_from_tool_events(tool_events)
        if artifact_refs:
            await workflow_svc.create_artifact(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                artifact_type="tool_references",
                storage_kind="inline_json",
                storage_ref={"items": artifact_refs},
                visibility="user",
                lifecycle="candidate",
                summary=f"{len(artifact_refs)} tool result reference id(s)",
            )
        run = await workflow_svc.get_workflow(db, self.run_id, user_id=self.owner_id)
        if run.status == "needs_confirmation":
            return
        if tool_events:
            tool_results = [event for event in tool_events if event.get("type") == "tool_result"]
            failed_results = [event for event in tool_results if _status_for_result(event) == "failed"]
            failed = bool(failed_results)
            await workflow_svc.record_verification(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                verification_type="tool_execution",
                status="fail" if failed else "pass",
                summary="Tool execution failed" if failed else "Tool execution completed",
                is_required_for_completion=True,
                evidence_ref={
                    "source": "tool_result",
                    "result": "fail" if failed else "pass",
                    "tool_event_count": len(tool_events),
                    "tool_result_count": len(tool_results),
                    "failed_count": len(failed_results),
                    "artifact_refs": artifact_refs,
                },
            )
        else:
            await workflow_svc.record_verification(
                db,
                run_id=self.run_id,
                step_id=self.step_id,
                verification_type="no_side_effect",
                status="pass",
                summary="No tool side effects were produced",
                is_required_for_completion=True,
                evidence_ref={"source": "runtime", "result": "pass"},
            )
        if self.step_id:
            await workflow_svc.update_step_status(
                db,
                self.step_id,
                status="completed",
                run_id=self.run_id,
                summary="Agent turn completed",
                output_ref={"message_id": message_id, "tool_event_count": len(tool_events)},
            )
        await workflow_svc.finalize_workflow(db, run_id=self.run_id, developer_summary="Finalized by Agent runtime link")

    async def record_runtime_failure(
        self,
        db: AsyncSession,
        *,
        error_type: str,
        error_message: str,
    ) -> None:
        await self.ensure_started(db, reason="runtime_failure")
        signature = _truncate(f"{error_type}: {error_message}", 256)
        await workflow_svc.record_failure(
            db,
            run_id=self.run_id,
            step_id=self.step_id,
            failure_type="tool_error",
            error_signature=signature,
            retryable=False,
            next_action="manual",
            evidence_ref={"error_type": error_type, "message": _truncate(error_message, 1000)},
            handoff_note=signature,
        )
        await workflow_svc.record_verification(
            db,
            run_id=self.run_id,
            step_id=self.step_id,
            verification_type="runtime_exception",
            status="fail",
            summary=signature,
            is_required_for_completion=True,
        )
        if self.step_id:
            await workflow_svc.update_step_status(
                db,
                self.step_id,
                status="failed",
                run_id=self.run_id,
                summary=signature,
                error_class=error_type,
                error_signature=signature,
            )
        await workflow_svc.finalize_workflow(db, run_id=self.run_id, developer_summary="Runtime exception")
