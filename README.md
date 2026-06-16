# Huashiwangzu V2

Huashiwangzu V2 is a rebuilt desktop-style business platform.

## Current Architecture

```text
frontend/   Vue desktop shell
backend/    FastAPI platform service layer
modules/    Business modules and desktop apps
开发文档/     User-facing development documentation
```

The old Laravel/PHP tree is no longer part of V2. Missing behavior should be referenced from V1 or historical versions, then rebuilt under the V2 architecture.

## Technology Stack

| Layer | Stack |
|---|---|
| Frontend | Vue 3, TypeScript, Vite, Element Plus |
| Backend | Python 3.14+, FastAPI, SQLAlchemy async |
| Database | PostgreSQL 17, pgvector |
| Module model | `modules/*/manifest.json` plus mandatory sandbox self-test |

## Documentation

Start here:

```text
开发文档/README.md
```

Agent rules:

```text
AGENTS.md
```

## Common Commands

```bash
cd backend && pytest
cd frontend && npm run build
```

