---
name: "scheduler r2 evidence findings before fix"
type: "task"
tags: [scheduler, r2, evidence, validation, sandbox]
agent: "codex-scheduler-followup-sweep-20260703-r2"
created: "2026-07-03T08:06:40.850577+00:00"
---

Evidence checkpoint before edits. CodeGraph shows scheduler backend is isolated to modules/scheduler/backend/router.py with impact only to that file; sandbox impact only to modules/scheduler/sandbox/test_module.py. Live capability checks confirm empty title and invalid task_id return structured 422 envelopes; list is owner-scoped and currently empty for viewer. Framework worker uses framework_system_task_queues with FOR UPDATE SKIP LOCKED, so worker state is DB-backed/cross-worker. Findings to fix in module scope: scheduled_at in the past is silently treated as due/immediate, duplicate pending scheduler tasks are not rejected, capability cancel should explicitly reject unresolved caller id, and sandbox tests duplicate validation logic instead of importing production scheduler validation/helpers.
