"""Cross-module capability registry（带元数据，支持技能发现）。"""
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Awaitable, Callable

from app.core.exceptions import ConflictError, NotFound, PermissionDenied

logger = logging.getLogger("v2.module_registry")

CapabilityHandler = Callable[[dict, str], Awaitable[dict]]
# key -> {handler, description, parameters, min_role}
_CAPABILITIES: dict[str, dict] = {}
_PRIVATE_REGISTRATION_OWNER: ContextVar[int | None] = ContextVar(
    "private_registration_owner",
    default=None,
)

_ROLE_ORDER = {"viewer": 0, "editor": 1, "admin": 2}

# 可信系统主体白名单：caller 以 system: 开头时从此处获取角色
_SERVICE_PRINCIPAL_ROLES = {
    "system:agent-engine": "admin",
    "system:app-loader": "admin",
    "system:task-worker": "admin",
}


def _key(module_key: str, action: str) -> str:
    return f"{module_key}:{action}"


def _non_empty_error(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _legacy_code_failure(value: object) -> bool:
    if value in (None, "", 0, "0"):
        return False
    if isinstance(value, bool):
        return value is not False
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            return float(text) != 0
        except ValueError:
            return False
    return False


def semantic_failure_reason(result: object, *, _path: str = "result", _depth: int = 0) -> str | None:
    """Return a reason when a result payload is semantically failed.

    This is the shared boundary rule for module calls and background task
    results. It intentionally treats non-empty ``error`` as failure even when
    an outer transport envelope says success=true.
    """
    if _depth > 8:
        return None
    if isinstance(result, str):
        text = result.strip()
        if not text or text[0] not in "{[":
            return None
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(result, dict):
        return None

    if result.get("success") is False:
        return _non_empty_error(result.get("error")) or f"{_path}.success=false"

    error = _non_empty_error(result.get("error"))
    if error:
        return error

    status = result.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error"}:
        return _non_empty_error(result.get("error")) or f"{_path}.status={status}"

    if "code" in result and _legacy_code_failure(result.get("code")):
        return (
            _non_empty_error(result.get("message"))
            or _non_empty_error(result.get("msg"))
            or _non_empty_error(result.get("error"))
            or f"{_path}.code={result.get('code')}"
        )

    for key in ("data", "result"):
        inner = result.get(key)
        if isinstance(inner, (dict, str)):
            inner_reason = semantic_failure_reason(inner, _path=f"{_path}.{key}", _depth=_depth + 1)
            if inner_reason:
                return inner_reason
    return None


def _current_capability_keys() -> set[str]:
    """Return the current set of all registered capability keys.

    Used by private_module_service to track which capabilities a
    private module registers during activation, so they can be
    properly cleaned up on deactivation.
    """
    return set(_CAPABILITIES.keys())


def _current_capability_snapshot() -> dict[str, dict]:
    """Return a shallow snapshot of capability entries for activation rollback."""
    return {key: dict(value) for key, value in _CAPABILITIES.items()}


def _restore_capability_snapshot(snapshot: dict[str, dict]) -> None:
    """Restore registry state after a failed dynamic module activation."""
    _CAPABILITIES.clear()
    _CAPABILITIES.update({key: dict(value) for key, value in snapshot.items()})


@contextmanager
def private_capability_registration(owner_id: int) -> Iterator[None]:
    """Scope import-time capability registration to a private module owner."""
    token = _PRIVATE_REGISTRATION_OWNER.set(owner_id)
    try:
        yield
    finally:
        _PRIVATE_REGISTRATION_OWNER.reset(token)


def register_capability(
    module_key: str,
    action: str,
    handler: CapabilityHandler,
    description: str = "",
    parameters: dict | None = None,
    min_role: str = "viewer",
    brief: str = "",
    owner_id: int | None = None,
) -> None:
    """模块注册一个对外能力。owner_id 非空时标识该能力为私有,仅对应 owner 可调用。"""
    scoped_owner_id = owner_id
    implicit_owner_id = _PRIVATE_REGISTRATION_OWNER.get()
    if scoped_owner_id is None and implicit_owner_id is not None:
        scoped_owner_id = implicit_owner_id

    key = _key(module_key, action)
    existing = _CAPABILITIES.get(key)
    if implicit_owner_id is not None and existing and existing.get("owner_id") != scoped_owner_id:
        raise ConflictError(f"Private capability cannot override existing capability: {key}")

    _CAPABILITIES[key] = {
        "handler": handler,
        "description": description,
        "parameters": parameters or {},
        "min_role": min_role,
        "brief": brief or description[:20],
        "owner_id": scoped_owner_id,
    }
    logger.info(
        "Registered capability: %s:%s (scope=%s)",
        module_key, action,
        f"private:owner={scoped_owner_id}" if scoped_owner_id else "public",
    )


def unregister_capability(module_key: str, action: str | None = None) -> None:
    """移除模块注册的能力。action 为 None 时移除该模块所有能力。"""
    if action:
        _CAPABILITIES.pop(_key(module_key, action), None)
    else:
        prefix = f"{module_key}:"
        keys_to_remove = [k for k in _CAPABILITIES if k.startswith(prefix)]
        for k in keys_to_remove:
            _CAPABILITIES.pop(k, None)
        logger.info("Unregistered all capabilities for module: %s", module_key)


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

    如果能力注册了 owner_id，则只有该 owner（user:{owner_id} 或 system: 白名单）可调用。
    """
    entry = _CAPABILITIES.get(_key(target_module, action))
    if not entry:
        raise NotFound(f"Module '{target_module}' does not expose action '{action}'")

    # Owner isolation check: private capabilities are only callable by their owner
    capability_owner = entry.get("owner_id")
    if capability_owner is not None:
        if caller.startswith("user:"):
            caller_id = int(caller.split(":", 1)[1])
            if caller_id != capability_owner:
                raise PermissionDenied(
                    f"Private capability '{target_module}:{action}' is owned by user {capability_owner}"
                )
        elif not caller.startswith("system:"):
            raise PermissionDenied(f"Invalid caller format: {caller}")

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


def _caller_owner_id(caller: str | None) -> int | None:
    if not caller or not caller.startswith("user:"):
        return None
    try:
        return int(caller.split(":", 1)[1])
    except ValueError:
        return None


def list_capabilities(role: str | None = None, caller: str | None = None) -> list[dict]:
    """列出能力元数据（不含 handler）。传 role 则按权限过滤（只返回该角色可调的）。"""
    caller_owner_id = _caller_owner_id(caller)
    include_all_private = bool(caller and caller.startswith("system:"))
    result = []
    for k, e in _CAPABILITIES.items():
        if role and _ROLE_ORDER.get(role, 0) < _ROLE_ORDER.get(e["min_role"], 0):
            continue
        capability_owner = e.get("owner_id")
        if capability_owner is not None and not include_all_private and capability_owner != caller_owner_id:
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
