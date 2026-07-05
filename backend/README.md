# Backend

The backend is the FastAPI platform service layer. It provides shared capabilities for the desktop shell and modules; business workflows belong in `modules/`.

## Responsibilities

- Application and router registration.
- PostgreSQL async sessions and migrations.
- Auth, roles, permissions, and unified API errors.
- File storage, preview, recycle, sharing, and audit logs.
- Task queues, workers, event bus, and scheduled tasks.
- Model gateway, embedding, rerank, and vision description.
- Content IR, ContentPackage, Resource, and Artifact services.

## Runtime

| Item | Current contract |
|---|---|
| Python | 3.14+ |
| Backend port | `127.0.0.1:33000` |
| Database | PostgreSQL 17 + pgvector |
| App entry | `backend/app/main.py` |
| Start script | `scripts/start_backend.sh` |

## Commands

```bash
cd backend && .venv/bin/python -m pytest
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 33000
```

Use project toolkit `probe`, `routes`, `db_schema`, and `tail_log` for live inspection.
