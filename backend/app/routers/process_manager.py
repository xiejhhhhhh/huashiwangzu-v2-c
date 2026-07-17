"""全盘进程管理器 HTTP 接口。

华哥要的"网站内部的全盘资源管理器":一张表看清所有后台进程是谁、
PID/稳定token、日志在哪、是否暴毙。找 bug 不用再 ps grep 瞎翻。
配合资源底座(/api/system-status 那套 CPU/GPU):资源底座=机器剩多少力,本表=力被谁占了。
"""
from fastapi import APIRouter, Depends

from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.process_registry import (
    列出活进程,
    巡检对账,
    按token找回,
)

router = APIRouter(prefix="/api/process-manager", tags=["process-manager"])


@router.get("/list")
async def 列进程(
    含判活: bool = True,
    _user: User = Depends(require_permission("admin")),
):
    """列出所有 running 后台进程,实时标 alive/暴毙。"""
    进程 = await 列出活进程(含判活=含判活)
    活 = sum(1 for p in 进程 if p.get("alive") is True)
    暴毙 = sum(1 for p in 进程 if p.get("暴毙") is True)
    return ApiResponse(data={"进程": 进程, "总数": len(进程), "存活": 活, "暴毙": 暴毙})


@router.post("/reconcile")
async def 巡检(
    心跳超时秒: int = 0,
    _user: User = Depends(require_permission("admin")),
):
    """主动巡检对账:把 pid已死/被回收复用/心跳超时的进程标 stale。返回标记数。"""
    n = await 巡检对账(心跳超时秒=心跳超时秒)
    return ApiResponse(data={"标记暴毙数": n})


@router.get("/find/{run_token}")
async def 找回(
    run_token: str,
    _user: User = Depends(require_permission("admin")),
):
    """靠稳定 token 找回一条进程记录(PID 变了也能找到),带判活结论。"""
    r = await 按token找回(run_token)
    if r is None:
        return ApiResponse(success=False, error="没找到该 token 的进程记录", data=None)
    return ApiResponse(data=r)
