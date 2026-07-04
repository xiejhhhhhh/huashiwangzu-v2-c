# scheduler — Scheduled task manager

## Responsibility
Creates, lists, and cancels scheduled tasks. Tasks are stored in the framework's `SystemTaskQueue` and executed by the framework worker. On execution, results are pushed to the user via the `im:notify` capability.

## Public capabilities

| Capability | Parameters | Returns | min_role |
|---|---|---|---|
| `scheduler:create` | `title` (str), `action_description` (str), `scheduled_at` (str?), `recur` (str?) | `{id}` | editor |
| `scheduler:list` | (none) | `[{id, title, status, scheduled_at, recur, ...}]` | viewer |
| `scheduler:cancel` | `task_id` (int) | `{id, status}` | editor |

Recurrence: `hourly` / `daily` / `weekly` / `cron:HH:MM`.

## HTTP endpoints

All under `/api/scheduler`:

| Method | Path | Purpose |
|---|---|---|
| POST | `/create` | Create a scheduled task |
| GET | `/list` | List current user's scheduled tasks |
| POST | `/cancel` | Cancel a pending scheduled task |

## Data tables
None. Uses framework's `framework_system_task_queues` table (module="scheduler") for persistence.

## How to query/use
Agent calls `scheduler:create` to schedule future actions, `scheduler:list` to review, `scheduler:cancel` to abort. All via `call_capability("scheduler", "create", {...})`.

## Verification

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/scheduler/sandbox/test_module.py
python3.14 scripts/check-capability-drift.py
```

## Boundaries/notes
- `scheduled_at` ISO 8601 format; if empty, runs immediately.
- `recur` supports hourly, daily, weekly, or cron:HH:MM (UTC).
- Task execution handler `scheduled_agent_job` is registered with `register_task_handler`.
- On execution, pushes notification via `im:notify` (falls back to log if IM unavailable).
- Only the task creator can list/cancel their own tasks.
- `creator_id` isolation enforced at API and capability levels.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `scheduler`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 3 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | SKIP | Module does not directly consume framework file_id content. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/scheduler/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `scheduler:<action>` and release smoke/capability drift gates. |
| Known debt | PASS | None tracked in this matrix. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/scheduler/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module scheduler --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
