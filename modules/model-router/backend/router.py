"""模型路由管理器后端路由。

管理 backend/data/config/models.json 这份"模型路由唯一数据源"文件：
    - providers：底层模型服务商连接信息（API 地址 / 密钥环境变量名）
    - model_types.*.profiles：具体可选模型档案（llm/vision/embedding/rerank/image_gen）
    - fallback_policies：显式声明的降级链
    - module_routing：各业务模块（目前只有 knowledge）按 stage 绑定的 profile

本模块在此基础上抽出一层"调用节点"（NODE_DEFINITIONS）：把散落在 models.json
各处的具体配置项，映射成运营/管理同事能看懂的业务节点（比如"知识库-OCR"），
每个节点对应到 models.json 里唯一一条可写路径，前端只需要给节点选一个同类型
profile，不用理解 JSON 结构。

写操作统一走 _save_config()：读当前文件 -> 改字段 -> JSON 校验 -> 落盘备份
-> 写回 models.json -> 调 app.gateway.config.reload_config() 热刷新缓存，
同时重建 gateway_router 的 provider 实例（provider 配置可能已变化）。

权限：本模块是纯管理工具，所有接口（含只读）都要求 admin 角色。
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.exceptions import ConflictError, NotFound, ValidationError
from app.gateway.config import (
    get_models_config,
    get_models_config_path,
    reload_config,
    resolve_api_key,
)
from app.middleware.auth import require_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("v2.model_router.api")
router = APIRouter(prefix="/api/model-router", tags=["model-router"])

# ── 路径常量 ──
# 本文件位于 modules/model-router/backend/router.py，parents[3] 就是项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = _PROJECT_ROOT / "backend"
_BACKUPS_DIR = _BACKEND_DIR / "backups"

# ── 调用节点定义 ──
# 每个节点对应 models.json 里一条"当前使用哪个 profile"的可写路径。
# config_path 指向的位置如果本身是一个字典（如 "model_types.llm"），
# 取/写它的 "primary" 字段；如果指向的是标量（如
# "module_routing.knowledge.default_profile"），直接取/写该字段本身。
# 这套规则由 _resolve_node_slot() 统一处理，节点定义本身不用关心这个区别。
#
# model_type 决定下拉候选池：候选永远来自 model_types.{model_type}.profiles，
# 与 config_path 实际写入的位置无关（哪怕 config_path 落在
# module_routing.knowledge.stages 下面）。
#
# agent_chat / agent_planning 的 profile_source 是提示信息：Agent 模块的
# Python 代码里把 "deepseek-v4-flash" 写死在多处调用点，并不会读
# model_types.llm.primary。这两个节点的 config_path 目前都指向同一个
# model_types.llm.primary 字段——这是已知的局限（改一个会影响另一个的
# 显示值），profile_source 只用来在 GET /nodes 里提示"代码里实际写死的值"，
# 帮管理员发现 JSON 配置和代码硬编码之间的落差，PUT 写入仍然落到
# model_types.llm.primary，不会去改 Python 代码。
NODE_DEFINITIONS: list[dict[str, Any]] = [
    {"id": "agent_chat", "name": "Agent 对话", "model_type": "llm", "config_path": "model_types.llm", "profile_source": "deepseek-v4-flash", "group": "agent"},
    {"id": "agent_planning", "name": "Agent 规划", "model_type": "llm", "config_path": "model_types.llm", "profile_source": "deepseek-v4-flash", "group": "agent"},
    {"id": "knowledge_text", "name": "知识库-文本分析", "model_type": "llm", "config_path": "module_routing.knowledge.default_profile", "group": "knowledge"},
    {"id": "knowledge_vision", "name": "知识库-视觉分析", "model_type": "vision", "config_path": "module_routing.knowledge.default_vision_profile", "group": "knowledge"},
    {"id": "knowledge_ocr", "name": "知识库-OCR", "model_type": "vision", "config_path": "module_routing.knowledge.stages.raw_ocr", "group": "knowledge"},
    {"id": "knowledge_fusion", "name": "知识库-融合", "model_type": "llm", "config_path": "module_routing.knowledge.stages.fusion", "group": "knowledge"},
    {"id": "knowledge_profile", "name": "知识库-摘要画像", "model_type": "llm", "config_path": "module_routing.knowledge.stages.profile", "group": "knowledge"},
    {"id": "knowledge_entity", "name": "知识库-实体提取", "model_type": "llm", "config_path": "module_routing.knowledge.stages.entity", "group": "knowledge"},
    {"id": "image_gen", "name": "生图", "model_type": "image_gen", "config_path": "model_types.image_gen", "group": "tools"},
    {"id": "vision", "name": "通用视觉", "model_type": "vision", "config_path": "model_types.vision", "group": "tools"},
    {"id": "embedding", "name": "向量嵌入", "model_type": "embedding", "config_path": "model_types.embedding", "group": "tools"},
    {"id": "rerank", "name": "重排序", "model_type": "rerank", "config_path": "model_types.rerank", "group": "tools"},
]
_NODE_MAP: dict[str, dict[str, Any]] = {node["id"]: node for node in NODE_DEFINITIONS}

# 密钥字段名黑名单：出现在 provider/config 里绝不允许原样返回给前端
_SECRET_FIELD_NAMES = {"api_key", "secret", "access_key", "secret_key", "password", "token"}


# ── models.json 点路径读写 ──

def _get_by_path(config: dict, dotted_path: str) -> Any:
    """按 "a.b.c" 点路径读取嵌套字典里的值，找不到返回 None。"""
    node: Any = config
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_by_path(config: dict, dotted_path: str, value: Any) -> None:
    """按 "a.b.c" 点路径写入嵌套字典，中间层级不存在时原地创建空字典。"""
    parts = dotted_path.split(".")
    node = config
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value


def _resolve_node_slot(config: dict, node_def: dict) -> tuple[str, str]:
    """把节点定义的 config_path 解析成真正要读写的 (容器点路径, 字段名)。

    如果 config_path 指向的是字典（如 "model_types.llm"），实际读写它下面的
    "primary" 字段；否则 config_path 本身就是要读写的标量字段，容器路径是
    它的父路径。
    """
    raw_path = node_def["config_path"]
    value_at_path = _get_by_path(config, raw_path)
    if isinstance(value_at_path, dict):
        return raw_path, "primary"
    if "." not in raw_path:
        return "", raw_path
    container_path, field = raw_path.rsplit(".", 1)
    return container_path, field


def _node_current_profile(config: dict, node_def: dict) -> str | None:
    container_path, field = _resolve_node_slot(config, node_def)
    container = _get_by_path(config, container_path) if container_path else config
    if not isinstance(container, dict):
        return None
    val = container.get(field)
    return str(val) if val else None


def _node_set_profile(config: dict, node_def: dict, profile_key: str) -> None:
    container_path, field = _resolve_node_slot(config, node_def)
    if container_path:
        _set_by_path(config, f"{container_path}.{field}", profile_key)
    else:
        config[field] = profile_key


def _mask_provider(key: str, cfg: dict) -> dict:
    """provider 配置对外展示：密钥字段只保留环境变量名，不泄露实际值。"""
    masked = dict(cfg)
    for field_name in list(masked.keys()):
        lowered = field_name.lower()
        if lowered in _SECRET_FIELD_NAMES or lowered.endswith("_key") and "_env" not in lowered:
            # api_key_env 之类保留（本身就是变量名，不是值），真正的值字段才隐藏
            if not lowered.endswith("_env"):
                masked.pop(field_name, None)
    masked["key"] = key
    masked["api_key_env"] = cfg.get("api_key_env", "")
    return masked


def _all_profile_keys(config: dict) -> set[str]:
    keys: set[str] = set()
    for type_cfg in config.get("model_types", {}).values():
        if isinstance(type_cfg, dict):
            keys.update(type_cfg.get("profiles", {}).keys())
    return keys


def _profiles_for_type(config: dict, model_type: str) -> dict[str, dict]:
    return config.get("model_types", {}).get(model_type, {}).get("profiles", {})


def _providers_referencing(config: dict, provider_key: str) -> list[str]:
    """返回所有引用了某 provider 的 profile key（跨全部 model_type）。"""
    refs: list[str] = []
    for type_name, type_cfg in config.get("model_types", {}).items():
        if not isinstance(type_cfg, dict):
            continue
        for profile_key, profile_cfg in type_cfg.get("profiles", {}).items():
            if isinstance(profile_cfg, dict) and profile_cfg.get("provider") == provider_key:
                refs.append(f"{type_name}.{profile_key}")
    return refs


def _nodes_referencing_profile(config: dict, profile_key: str) -> list[str]:
    """返回所有当前指向某 profile 的节点 id。"""
    refs: list[str] = []
    for node_def in NODE_DEFINITIONS:
        if _node_current_profile(config, node_def) == profile_key:
            refs.append(node_def["id"])
    return refs


def _iter_all_profiles(config: dict) -> Iterable[tuple[str, str, dict]]:
    """遍历所有 (model_type, profile_key, profile_cfg)。"""
    for type_name, type_cfg in config.get("model_types", {}).items():
        if not isinstance(type_cfg, dict):
            continue
        for profile_key, profile_cfg in type_cfg.get("profiles", {}).items():
            if isinstance(profile_cfg, dict):
                yield type_name, profile_key, profile_cfg


# ── 落盘：读取/校验/备份/写回/热刷新 ──

def _read_current_config() -> dict:
    """直接读磁盘上的 models.json（不走 gateway 的内存缓存），确保写操作前拿到最新内容。"""
    path = get_models_config_path()
    if not path.exists():
        raise NotFound(f"配置文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_backup(config: dict) -> Path:
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = _BACKUPS_DIR / f"models_json_{stamp}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return backup_path


def _save_config(mutated_config: dict) -> None:
    """统一的写操作出口：备份旧文件 -> JSON 校验 -> 写回 -> 热刷新缓存。

    调用方需要先拿到修改前的 _read_current_config() 结果，在上面原地修改后
    传入本函数。备份的是修改前的旧内容（从磁盘重新读一份，防止调用方传进来
    的对象已经被就地改过导致备份和线上文件一样没意义）。
    """
    path = get_models_config_path()
    old_config = _read_current_config()
    _write_backup(old_config)

    # JSON 校验：dumps 一次确保可序列化，再 loads 回来确保结构没坏
    serialized = json.dumps(mutated_config, ensure_ascii=False, indent=2)
    json.loads(serialized)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(serialized)

    reload_config()
    _rebuild_gateway_providers()


def _rebuild_gateway_providers() -> None:
    """provider 配置（api_url/api_key_env 等）可能已变化，重建 gateway_router 的
    provider 实例缓存，否则要等下次进程重启才会生效。"""
    try:
        from app.gateway.router import ModelGatewayRouter, gateway_router

        fresh = ModelGatewayRouter()
        gateway_router._providers = fresh._providers  # noqa: SLF001 — 刻意刷新单例内部状态
    except Exception as exc:  # pragma: no cover - 防止热刷新失败拖垮写操作主流程
        logger.warning("Rebuild gateway providers after config write failed: %s", exc)


async def _health_for_providers(provider_keys: Iterable[str]) -> dict[str, bool]:
    """对指定 provider 子集做一次连通性探针，复用 gateway_router 已构建的 provider 实例。"""
    from app.gateway.router import gateway_router

    result: dict[str, bool] = {}
    for key in set(provider_keys):
        provider = gateway_router._providers.get(key)  # noqa: SLF001
        if provider is None:
            result[key] = False
            continue
        try:
            result[key] = await provider.check_health()
        except Exception as exc:
            logger.warning("Health probe failed for provider %s: %s", key, exc)
            result[key] = False
    return result


# ── 请求体 Pydantic 模型 ──

class NodeUpdateRequest(BaseModel):
    profile_key: str


class ProviderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str
    type: str
    api_url: str = ""
    api_key_env: str = ""
    provider_name: str = ""
    description: str = ""


class ProviderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model_type: str
    profile_key: str
    provider: str
    model: str


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model_type: str


class FallbackPolicyUpdateRequest(BaseModel):
    chain: list[str]
    description: str | None = None


# ── GET /nodes ──

@router.get("/nodes")
async def list_nodes(user: User = Depends(require_permission("admin"))):
    config = get_models_config()
    provider_health = await _health_for_providers(
        p.get("provider") for _, _, p in _iter_all_profiles(config)
    )
    items = []
    for node_def in NODE_DEFINITIONS:
        current_key = _node_current_profile(config, node_def)
        candidates = _profiles_for_type(config, node_def["model_type"])
        current_profile = candidates.get(current_key) if current_key else None
        provider_key = current_profile.get("provider") if isinstance(current_profile, dict) else None
        items.append({
            "id": node_def["id"],
            "name": node_def["name"],
            "group": node_def["group"],
            "model_type": node_def["model_type"],
            "config_path": node_def["config_path"],
            "profile_source": node_def.get("profile_source", ""),
            "current_profile": current_key,
            "provider": provider_key,
            "healthy": provider_health.get(provider_key) if provider_key else None,
            "candidates": sorted(candidates.keys()),
        })
    return ApiResponse(data={"nodes": items})


# ── PUT /nodes/{node_id} ──

@router.put("/nodes/{node_id}")
async def update_node(
    node_id: str,
    payload: NodeUpdateRequest,
    user: User = Depends(require_permission("admin")),
):
    node_def = _NODE_MAP.get(node_id)
    if not node_def:
        raise NotFound(f"调用节点不存在: {node_id}")

    config = _read_current_config()
    candidates = _profiles_for_type(config, node_def["model_type"])
    if payload.profile_key not in candidates:
        raise ValidationError(
            f"profile '{payload.profile_key}' 不属于模型类型 '{node_def['model_type']}'，"
            f"可选: {sorted(candidates.keys())}"
        )

    _node_set_profile(config, node_def, payload.profile_key)
    _save_config(config)
    logger.info("[model-router] node=%s profile -> %s by user=%s", node_id, payload.profile_key, user.username)
    return ApiResponse(data={"id": node_id, "current_profile": payload.profile_key})


# ── GET /providers ──

@router.get("/providers")
async def list_providers(user: User = Depends(require_permission("admin"))):
    config = get_models_config()
    providers = config.get("providers", {})
    items = [_mask_provider(key, cfg) for key, cfg in providers.items()]
    return ApiResponse(data={"providers": items})


# ── POST /providers ──

@router.post("/providers")
async def create_provider(
    payload: ProviderCreateRequest,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    providers = config.setdefault("providers", {})
    if payload.key in providers:
        raise ConflictError(f"provider '{payload.key}' 已存在")

    provider_body = payload.model_dump(exclude={"key"}, exclude_none=True)
    providers[payload.key] = provider_body
    _save_config(config)
    logger.info("[model-router] provider created: %s by user=%s", payload.key, user.username)
    return ApiResponse(data=_mask_provider(payload.key, provider_body))


# ── PUT /providers/{provider_key} ──

@router.put("/providers/{provider_key}")
async def update_provider(
    provider_key: str,
    payload: ProviderUpdateRequest,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    providers = config.get("providers", {})
    if provider_key not in providers:
        raise NotFound(f"provider 不存在: {provider_key}")

    updates = payload.model_dump(exclude_none=True)
    providers[provider_key].update(updates)
    _save_config(config)
    logger.info("[model-router] provider updated: %s by user=%s", provider_key, user.username)
    return ApiResponse(data=_mask_provider(provider_key, providers[provider_key]))


# ── DELETE /providers/{provider_key} ──

@router.delete("/providers/{provider_key}")
async def delete_provider(
    provider_key: str,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    providers = config.get("providers", {})
    if provider_key not in providers:
        raise NotFound(f"provider 不存在: {provider_key}")

    referenced_by = _providers_referencing(config, provider_key)
    if referenced_by:
        raise ConflictError(
            f"provider '{provider_key}' 仍被以下 profile 引用，无法删除: {referenced_by}"
        )

    del providers[provider_key]
    _save_config(config)
    logger.info("[model-router] provider deleted: %s by user=%s", provider_key, user.username)
    return ApiResponse(data={"deleted": provider_key})


# ── POST /providers/{provider_key}/test ──

@router.post("/providers/{provider_key}/test")
async def test_provider(
    provider_key: str,
    user: User = Depends(require_permission("admin")),
):
    config = get_models_config()
    provider_cfg = config.get("providers", {}).get(provider_key)
    if not provider_cfg:
        raise NotFound(f"provider 不存在: {provider_key}")

    result = await _health_for_providers([provider_key])
    healthy = result.get(provider_key, False)
    return ApiResponse(data={
        "provider": provider_key,
        "healthy": healthy,
        "api_url": provider_cfg.get("api_url", ""),
        "api_key_configured": bool(resolve_api_key(provider_cfg)) if provider_cfg.get("api_key_env") else None,
    })


# ── GET /profiles ──

@router.get("/profiles")
async def list_profiles(user: User = Depends(require_permission("admin"))):
    config = get_models_config()
    grouped: dict[str, list[dict]] = {}
    for type_name, type_cfg in config.get("model_types", {}).items():
        if not isinstance(type_cfg, dict):
            continue
        profiles = type_cfg.get("profiles", {})
        items = []
        for profile_key, profile_cfg in profiles.items():
            items.append({
                "key": profile_key,
                "is_primary": profile_key == type_cfg.get("primary"),
                "referenced_by_nodes": _nodes_referencing_profile(config, profile_key),
                **(profile_cfg if isinstance(profile_cfg, dict) else {}),
            })
        grouped[type_name] = items
    return ApiResponse(data={"profiles": grouped})


# ── POST /profiles ──

@router.post("/profiles")
async def create_profile(
    payload: ProfileCreateRequest,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    type_cfg = config.setdefault("model_types", {}).setdefault(payload.model_type, {})
    profiles = type_cfg.setdefault("profiles", {})
    if payload.profile_key in profiles:
        raise ConflictError(f"profile '{payload.profile_key}' 已存在于类型 '{payload.model_type}'")

    providers = config.get("providers", {})
    if payload.provider not in providers:
        raise ValidationError(f"provider '{payload.provider}' 不存在，请先创建 provider")

    profile_body = payload.model_dump(exclude={"model_type", "profile_key"}, exclude_none=True)
    profiles[payload.profile_key] = profile_body
    _save_config(config)
    logger.info(
        "[model-router] profile created: %s.%s by user=%s",
        payload.model_type, payload.profile_key, user.username,
    )
    return ApiResponse(data={"model_type": payload.model_type, "key": payload.profile_key, **profile_body})


# ── PUT /profiles/{profile_key} ──

@router.put("/profiles/{profile_key}")
async def update_profile(
    profile_key: str,
    payload: ProfileUpdateRequest,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    profiles = _profiles_for_type(config, payload.model_type)
    if profile_key not in profiles:
        raise NotFound(f"profile 不存在: {payload.model_type}.{profile_key}")

    updates = payload.model_dump(exclude={"model_type"}, exclude_none=True)
    if "provider" in updates and updates["provider"] not in config.get("providers", {}):
        raise ValidationError(f"provider '{updates['provider']}' 不存在")

    profiles[profile_key].update(updates)
    _save_config(config)
    logger.info(
        "[model-router] profile updated: %s.%s by user=%s",
        payload.model_type, profile_key, user.username,
    )
    return ApiResponse(data={"model_type": payload.model_type, "key": profile_key, **profiles[profile_key]})


# ── DELETE /profiles/{profile_key} ──

@router.delete("/profiles/{profile_key}")
async def delete_profile(
    profile_key: str,
    model_type: str,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    profiles = _profiles_for_type(config, model_type)
    if profile_key not in profiles:
        raise NotFound(f"profile 不存在: {model_type}.{profile_key}")

    referenced_by = _nodes_referencing_profile(config, profile_key)
    if referenced_by:
        raise ConflictError(
            f"profile '{profile_key}' 仍被以下调用节点引用，无法删除: {referenced_by}"
        )

    type_cfg = config.get("model_types", {}).get(model_type, {})
    if type_cfg.get("primary") == profile_key:
        raise ConflictError(f"profile '{profile_key}' 是类型 '{model_type}' 的主 primary，无法删除")

    del profiles[profile_key]
    _save_config(config)
    logger.info("[model-router] profile deleted: %s.%s by user=%s", model_type, profile_key, user.username)
    return ApiResponse(data={"deleted": profile_key, "model_type": model_type})


# ── POST /reload ──

@router.post("/reload")
async def reload(user: User = Depends(require_permission("admin"))):
    result = reload_config()
    _rebuild_gateway_providers()
    logger.info("[model-router] config reloaded by user=%s", user.username)
    return ApiResponse(data=result)


# ── GET /fallback-policies ──

@router.get("/fallback-policies")
async def list_fallback_policies(user: User = Depends(require_permission("admin"))):
    config = get_models_config()
    policies = config.get("fallback_policies", {})
    all_profiles = _all_profile_keys(config)
    items = []
    for key, policy in policies.items():
        chain = policy.get("chain", []) if isinstance(policy, dict) else []
        items.append({
            "key": key,
            "description": policy.get("description", "") if isinstance(policy, dict) else "",
            "chain": chain,
            "unknown_profiles_in_chain": [c for c in chain if c not in all_profiles],
        })
    return ApiResponse(data={"fallback_policies": items})


# ── PUT /fallback-policies/{policy_key} ──

@router.put("/fallback-policies/{policy_key}")
async def update_fallback_policy(
    policy_key: str,
    payload: FallbackPolicyUpdateRequest,
    user: User = Depends(require_permission("admin")),
):
    config = _read_current_config()
    policies = config.setdefault("fallback_policies", {})
    existing = policies.get(policy_key)
    if existing is None:
        raise NotFound(f"fallback policy 不存在: {policy_key}")

    unknown = [c for c in payload.chain if c not in _all_profile_keys(config)]
    if unknown:
        raise ValidationError(f"chain 中包含不存在的 profile: {unknown}")

    existing["chain"] = payload.chain
    if payload.description is not None:
        existing["description"] = payload.description
    _save_config(config)
    logger.info("[model-router] fallback policy updated: %s by user=%s", policy_key, user.username)
    return ApiResponse(data={"key": policy_key, **existing})

