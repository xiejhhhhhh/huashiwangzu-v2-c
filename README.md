# Huashiwangzu V2

Huashiwangzu V2 is a clean rebuild of a desktop-style business platform.

## Architecture

```text
frontend/   Vue desktop shell and platform UI
backend/    FastAPI platform service layer
modules/    Business modules and desktop apps
开发文档/    Current development documentation
```

## Start Here

- Agent hard rules: `AGENTS.md`
- Current project entry: `开发文档/README.md`
- Agent handoff workflow: `开发文档/agent_handoff/START_HERE.md`
- Toolkit MCP: `dev_toolkit/README.md`

## Core Commands

```bash
cd frontend && npm run build
cd backend && .venv/bin/python -m pytest
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```

Business behavior belongs in `modules/`. Framework capabilities belong in `frontend/` or `backend/`.
