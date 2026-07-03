"""Knowledge backend sandbox: real framework infrastructure + only knowledge router.

Development mode uses production DB/model gateway, but creates and touches only kb_* tables.
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ENV = PROJECT_ROOT / "backend" / ".env"
KNOWLEDGE_BACKEND = Path(__file__).resolve().parents[3] / "backend"


def _load_backend_env() -> None:
    if not BACKEND_ENV.exists():
        return
    for raw_line in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_backend_env()

from app.database import engine
from app.middleware.auth import get_current_user
from app.models.base import Base
from app.models.user import User
from app.services.module_registry import list_capabilities
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .huashiwangzu_modules_bootstrap import load_knowledge_router

knowledge_router = load_knowledge_router(KNOWLEDGE_BACKEND / "router.py")

app = FastAPI(title="Knowledge Sandbox Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5185", "http://localhost:5185"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(knowledge_router)


def _dev_user() -> User:
    user = User()
    user.id = 1
    user.username = "dev"
    user.role = "admin"
    return user


async def _mock_get_current_user():
    return _dev_user()


app.dependency_overrides[get_current_user] = _mock_get_current_user


@app.get("/api/knowledge/sandbox/capabilities")
async def capabilities():
    return {"success": True, "data": list_capabilities(role="admin"), "error": None}


@app.on_event("startup")
async def _startup():
    kb_tables = [table for name, table in Base.metadata.tables.items() if name.startswith("kb_")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=kb_tables))
