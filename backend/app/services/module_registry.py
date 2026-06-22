"""Cross-module capability registry（带元数据，支持技能发现）。"""
import logging
from typing import Awaitable, Callable

from app.core.exceptions import NotFound, PermissionDenied

logger = logging.getLogger("v2.module_registry")

CapabilityHandler = Callable[[dict, str], Awaitable[dict]]
# key -> {handler, description, parameters, min_role}
_CAPABILITIES: dict[str, dict] = {}

_ROLE_ORDER = {"viewer": 0, "editor": 1, "admin": 2}

# 可信系统主体白名单：caller 以 system: 开头时从此处获取角色
_SERVICE_PRINCIPAL_ROLES = {
    "system:agent-engine": "admin",
    "system:app-loader": "admin",
    "system:task-worker": "admin",
}


def _key(module_key: str, action: str) -> str:
    return f"{module_key}:{action}"


def register_capability(
    module_key: str,
    action: str,
    handler: CapabilityHandler,
    description: str = "",
    parameters: dict | None = None,
    min_role: str = "viewer",
    brief: str = "",
) -> None:
    """模块注册一个对外能力。description/parameters/min_role 供技能发现用。brief 供 skill_list 紧凑展示（≤20字）。"""
    _CAPABILITIES[_key(module_key, action)] = {
        "handler": handler,
        "description": description,
        "parameters": parameters or {},
        "min_role": min_role,
        "brief": brief or description[:20],
    }
    logger.info("Registered capability: %s:%s", module_key, action)


def _resolve_caller_role(caller: str, caller_role: str) -> str:
    """Resolve effective role from caller identity and caller_role parameter.

    - system:{principal}: role from _SERVICE_PRINCIPAL_ROLES whitelist
    - user:{id}: caller_role is accepted but capped; admin is logged as warning
    """
    if caller.startswith("system:"):
        principal_role = _SERVICE_PRINCIPAL_ROLES.get(caller)
        if principal_role is None:
            raise PermissionDenied(
                f"Unknown system principal: {caller}"
            )
        return principal_role
    if caller.startswith("user:"):
        if caller_role == "admin":
            logger.warning(
                "caller=%s passed caller_role='admin' — "
                "user callers should not pass admin role",
                caller,
            )
        return caller_role
    raise PermissionDenied(f"Invalid caller format: {caller}")


async def call_capability(
    target_module: str,
    action: str,
    params: dict,
    caller: str,
    caller_role: str = "viewer",
) -> dict:
    """跨模块调用的唯一入口。target 未公开或角色不足则抛异常。

    caller_role 对 user: 前缀的调用者不做严格审计（保持兼容），
    对 system: 前缀的调用者从 _SERVICE_PRINCIPAL_ROLES 白名单获取角色。
    """
    entry = _CAPABILITIES.get(_key(target_module, action))
    if not entry:
        raise NotFound(f"Module '{target_module}' does not expose action '{action}'")
    resolved_role = _resolve_caller_role(caller, caller_role)
    min_role = entry.get("min_role", "viewer")
    if _ROLE_ORDER.get(resolved_role, -1) < _ROLE_ORDER.get(min_role, 0):
        raise PermissionDenied(
            f"Requires at least '{min_role}' role, got '{resolved_role}'"
        )
    logger.info(
        "Cross-module call: caller=%s role=%s -> %s:%s",
        caller, resolved_role, target_module, action,
    )
    return await entry["handler"](params, caller)


def list_capabilities(role: str | None = None) -> list[dict]:
    """列出能力元数据（不含 handler）。传 role 则按权限过滤（只返回该角色可调的）。"""
    result = []
    for k, e in _CAPABILITIES.items():
        if role and _ROLE_ORDER.get(role, 0) < _ROLE_ORDER.get(e["min_role"], 0):
            continue
        module_key, action = k.split(":", 1)
        result.append({
            "module": module_key,
            "action": action,
            "description": e["description"],
            "parameters": e["parameters"],
            "min_role": e["min_role"],
            "brief": e.get("brief", e["description"][:20]),
        })
    return result


# 内置自检能力（带元数据示例）
async def _echo_capability(params: dict, caller: str) -> dict:
    return {"echo": params, "caller": caller}


register_capability(
    "_self", "echo", _echo_capability,
    description="回显输入参数，用于验证跨模块通路",
    parameters={"任意键值": "原样返回"},
    min_role="viewer",
)
