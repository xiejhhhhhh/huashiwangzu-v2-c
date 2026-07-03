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
