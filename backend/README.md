# Backend

The backend is the FastAPI platform service layer for V2. It provides shared platform capabilities for the desktop shell and business modules.

## Responsibilities

- FastAPI application and router registration.
- PostgreSQL connection, transactions, migrations, and ORM models.
- Authentication, roles, and permissions.
- Tasks, workers, and background jobs.
- Model watchdog and LLM gateway.
- File storage, upload, download, and preview support.
- System logs, health checks, backup, and restore.

Business workflows belong in `modules/`, not directly in the platform layer.

## Requirements

- Python 3.14+
- PostgreSQL 17
- pgvector
- Optional local `llama-server` for local model profiles

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Database

```bash
export V2_DATABASE_NAME="your_v2_database_name"
psql -U postgres -c "CREATE DATABASE \"$V2_DATABASE_NAME\";"
psql -U postgres -d "$V2_DATABASE_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -U postgres -d "$V2_DATABASE_NAME" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
alembic upgrade head
```

## Seed Data

```bash
V2_SEED_DEFAULT_PASSWORD='replace-with-a-strong-password' python -m app.seed
```

## Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 30004 --reload
```

Open API docs:

```text
http://127.0.0.1:30004/docs
```

## Test

```bash
pytest
```
