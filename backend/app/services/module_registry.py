"""Cross-module capability registry — unified governance control plane.

Governance fields shared across registry / events / task-worker / hooks:
  - module_key / owner          : identity
  - contract_version            : capability contract version (semver)
  - trusted_callers             : caller prefix whitelist (empty = all allowed)
  - timeout                     : per-call timeout in seconds
  - retry_policy                : {max_retries, backoff} for automatic retry
  - trace_id                    : cross-capability/event/retry trace chain
  - side_effect_level           : "readonly" | "low" | "medium" | "high"

This is the single control-plane entry point.  Module events (module_events.py)
SHARE the same governance metadata contract — see its docstring.
"""
import logging
import uuid
from typing import Awaitable, Callable
from datetime import datetime, timezone

from app.core.exceptions import NotFound, PermissionDenied

logger = logging.getLogger("v2.module_registry")

CapabilityHandler = Callable[[dict, str], Awaitable[dict]]
# key -> {handler, description, parameters, min_role, contract_version,
#         timeout, trusted_callers, side_effect_level, retry_policy}
_CAPABILITIES: dict[str, dict] = {}

_ROLE_ORDER = {"viewer": 0, "editor": 1, "admin": 2}

# Side effect severity levels — consumers check BEFORE calling
SIDE_EFFECT_READONLY = "readonly"
SIDE_EFFECT_LOW = "low"
SIDE_EFFECT_MEDIUM = "medium"
SIDE_EFFECT_HIGH = "high"
_SIDE_EFFECT_ORDER = {SIDE_EFFECT_READONLY: 0, SIDE_EFFECT_LOW: 1, SIDE_EFFECT_MEDIUM: 2, SIDE_EFFECT_HIGH: 3}

SIDE_EFFECT_LEVELS = list(_SIDE_EFFECT_ORDER.keys())

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
    contract_version: str = "1.0.0",
    timeout: float | None = None,
    trusted_callers: list[str] | None = None,
    side_effect_level: str = SIDE_EFFECT_MEDIUM,
    retry_policy: dict | None = None,
) -> None:
    """模块注册一个对外能力。

    Governance fields (shared control-plane contract with module_events.py):
      - contract_version : 能力契约版本号（模块升级能力签名时可递增）
      - timeout          : 能力调用超时秒数（None = 不限制）
      - trusted_callers  : 允许调用该能力的 caller 前缀白名单（空 list = 所有 caller 均可）
      - side_effect_level: 副作用等级，按 "readonly" < "low" < "medium" < "high" 排序
      - retry_policy     : 自动重试策略，如 {"max_retries": 2, "backoff": 1.0}
    """
    if side_effect_level not in _SIDE_EFFECT_ORDER:
        raise ValueError(f"Invalid side_effect_level: {side_effect_level}. Must be one of {SIDE_EFFECT_LEVELS}")
    _CAPABILITIES[_key(module_key, action)] = {
        "handler": handler,
        "description": description,
        "parameters": parameters or {},
        "min_role": min_role,
        "brief": brief or description[:20],
        "contract_version": contract_version,
        "timeout": timeout,
        "trusted_callers": trusted_callers or [],
        "side_effect_level": side_effect_level,
        "retry_policy": retry_policy or {},
    }
    logger.info(
        "Registered capability: %s:%s (contract=%s side_effect=%s callers=%s)",
        module_key, action, contract_version, side_effect_level,
        len(trusted_callers or []),
    )


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
    trace_id: str | None = None,
    retry_attempt: int = 0,
) -> dict:
    """跨模块调用的唯一入口。target 未公开或角色不足则抛异常。

    trace_id    : 调用方传入的追踪 ID，用于跨能力/事件/重试的诊断串联。
    retry_attempt: 当前重试序号（由上游 RetryBudget 或 fallback 链传入）。
    返回 dict 含 _trace 字段（trace_id + 能力元数据快照 + 治理信息）。
    """
    trace_id = trace_id or str(uuid.uuid4())
    entry = _CAPABILITIES.get(_key(target_module, action))
    if not entry:
        raise NotFound(f"Module '{target_module}' does not expose action '{action}'")

    resolved_role = _resolve_caller_role(caller, caller_role)
    min_role = entry.get("min_role", "viewer")
    if _ROLE_ORDER.get(resolved_role, -1) < _ROLE_ORDER.get(min_role, 0):
        raise PermissionDenied(
            f"Requires at least '{min_role}' role, got '{resolved_role}'"
        )

    # trusted_callers enforcement
    trusted = entry.get("trusted_callers", [])
    if trusted:
        allowed = any(caller.startswith(p) for p in trusted)
        if not allowed:
            raise PermissionDenied(
                f"caller='{caller}' is not in trusted_callers={trusted} for {target_module}:{action}"
            )

    logger.info(
        "Cross-module call: caller=%s role=%s -> %s:%s trace=%s attempt=%d",
        caller, resolved_role, target_module, action, trace_id, retry_attempt,
    )
    result = await entry["handler"](params, caller)
    result["_trace"] = {
        "trace_id": trace_id,
        "module": target_module,
        "action": action,
        "contract_version": entry.get("contract_version", "1.0.0"),
        "timeout": entry.get("timeout"),
        "side_effect_level": entry.get("side_effect_level", SIDE_EFFECT_MEDIUM),
        "trusted_callers": entry.get("trusted_callers", []),
        "retry_policy": entry.get("retry_policy", {}),
        "retry_attempt": retry_attempt,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    return result


def list_capabilities(role: str | None = None) -> list[dict]:
    """列出能力元数据（不含 handler）。传 role 则按权限过滤（只返回该角色可调的）。

    Returns full governance metadata for each capability:
      module / action / description / parameters / min_role / brief /
      contract_version / timeout / trusted_callers / side_effect_level / retry_policy
    This is the control-plane view consumed by /api/modules/capabilities.
    """
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
            "contract_version": e.get("contract_version", "1.0.0"),
            "timeout": e.get("timeout"),
            "trusted_callers": e.get("trusted_callers", []),
            "side_effect_level": e.get("side_effect_level", SIDE_EFFECT_MEDIUM),
            "retry_policy": e.get("retry_policy", {}),
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
    side_effect_level="readonly",
    retry_policy={"max_retries": 0, "backoff": 0},
)
