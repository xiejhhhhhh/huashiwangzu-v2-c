"""预处理 / 任务 / 投影 / 迁移 状态枚举(方案07 §19.4 冻结)。

只保留这一套枚举,禁止文档与代码并存多套状态。存量 framework_content_packages.status
现有值只有 parsed/archived/degraded/stale,迁移按下表统一(§19.4):
    parsed   -> ready
    archived -> archived
    degraded -> degraded
    stale    -> stale
    draft    仅由 Office 新建草稿产生
    failed   仅由 Ingestion 终态失败写入

FileRevision.origin 值域: user_import | projection | external_replace
旧 framework_content_packages.origin_type(uploaded/generated) 停用为兼容镜像,
血缘以 FileRevision.origin 为准: uploaded->user_import, generated->projection。
"""
from __future__ import annotations

from typing import Literal

# --- Package 生命周期状态 --------------------------------------------------
PackageStatus = Literal[
    "draft",      # Office 新建草稿,尚无 SourceFile
    "ready",      # 解析完成、有合法 current version
    "degraded",   # 部分特性未支持,降级可用
    "failed",     # 终态失败
    "stale",      # 原件已变化,待重新预处理
    "archived",   # 归档
]
PACKAGE_STATUS_VALUES: tuple[str, ...] = (
    "draft", "ready", "degraded", "failed", "stale", "archived",
)

# 存量 status -> 冻结 status 迁移映射(§19.4)
LEGACY_PACKAGE_STATUS_MAP: dict[str, str] = {
    "parsed": "ready",
    "archived": "archived",
    "degraded": "degraded",
    "stale": "stale",
    # draft / failed 无存量来源,由新逻辑产生
}

# --- Ingestion 运行状态 ----------------------------------------------------
IngestionStatus = Literal[
    "queued",
    "running",
    "waiting_retry",
    "paused",
    "cancelling",
    "completed",
    "degraded",
    "failed",
    "dead_letter",
    "cancelled",
]
INGESTION_STATUS_VALUES: tuple[str, ...] = (
    "queued", "running", "waiting_retry", "paused", "cancelling",
    "completed", "degraded", "failed", "dead_letter", "cancelled",
)
INGESTION_TERMINAL_STATES: frozenset[str] = frozenset(
    {"completed", "degraded", "failed", "dead_letter", "cancelled"}
)

# --- Stage / Task 状态 -----------------------------------------------------
StageStatus = Literal[
    "blocked",
    "pending",
    "running",
    "retry_wait",
    "succeeded",
    "degraded",
    "skipped",
    "failed",
    "dead_letter",
    "cancelled",
]
STAGE_STATUS_VALUES: tuple[str, ...] = (
    "blocked", "pending", "running", "retry_wait", "succeeded",
    "degraded", "skipped", "failed", "dead_letter", "cancelled",
)

# --- Projection 状态 -------------------------------------------------------
ProjectionStatus = Literal[
    "queued", "building", "ready", "failed", "superseded",
]
PROJECTION_STATUS_VALUES: tuple[str, ...] = (
    "queued", "building", "ready", "failed", "superseded",
)

# --- Migration 状态 --------------------------------------------------------
MigrationStatus = Literal[
    "planned", "running", "paused", "validated", "failed",
    "rolled_back", "completed",
]
MIGRATION_STATUS_VALUES: tuple[str, ...] = (
    "planned", "running", "paused", "validated", "failed",
    "rolled_back", "completed",
)

# --- Stage DAG 固定顺序(§19.4) --------------------------------------------
STAGE_DAG: tuple[str, ...] = (
    "package_ensure",
    "canonical_parse",
    "resource_extract",
    "derivative_build",
    "knowledge_register",
)

# --- FileRevision.origin 值域(§19.1/§19.4) --------------------------------
FileRevisionOrigin = Literal["user_import", "projection", "external_replace"]
FILE_REVISION_ORIGIN_VALUES: tuple[str, ...] = (
    "user_import", "projection", "external_replace",
)
LEGACY_ORIGIN_TYPE_MAP: dict[str, str] = {
    "uploaded": "user_import",
    "generated": "projection",
}

# --- 本轮施工:越过模型密集节点的 defer 标记(方案07 §24) ------------------
# canonical_parse 对需模型格式先落 metadata_only;知识库语义派生/VLM/embedding
# 越过时 stage 标 skipped 并记录该 reason,禁止标 succeeded/ready 假绿。
MODEL_BUDGET_DEFERRED_REASON = "model_budget_deferred"
