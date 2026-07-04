"""Agent 后端 sandbox：借框架基础设施 + 生产库 + 真 gateway，只挂 Agent 路由。
专注开发 Agent，不用起整个桌面壳。只碰 agent_ 表，不碰其他模块。"""
import sys
from pathlib import Path

# 让本进程能 import 主框架 app.* 和 agent 模块代码
BACKEND_ROOT = Path(__file__).resolve().parents[4] / "backend"   # 主框架 backend/
AGENT_BACKEND = Path(__file__).resolve().parents[2] / "backend"  # modules/agent/backend/
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(AGENT_BACKEND))

from app.database import engine  # 直接用框架的生产库连接（调用框架，允许）
from app.middleware.auth import get_current_user  # 覆盖鉴权起点，比覆盖 require_permission 工厂可靠
from app.models.base import Base
from app.models.user import User
from fastapi import FastAPI

# 导入 agent 自己的 models（注册到 Base.metadata）和 router
from modules.agent.backend import models as agent_models  # noqa: F401
from modules.agent.backend.router import router as agent_router

app = FastAPI(title="Agent Sandbox Backend")
app.include_router(agent_router)


# —— 开发期固定测试用户（省登录）；模型/数据库都用真的 ——
def _dev_user() -> User:
    u = User()
    u.id = 1
    u.username = "dev"
    u.role = "admin"
    return u


async def _mock_get_current_user():
    return _dev_user()


app.dependency_overrides[get_current_user] = _mock_get_current_user


@app.on_event("startup")
async def _startup():
    # 在生产库建 agent 自己的表（只建 agent_ 前缀，绝不碰其他表）
    agent_tables = [t for n, t in Base.metadata.tables.items() if n.startswith("agent_")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=agent_tables))
