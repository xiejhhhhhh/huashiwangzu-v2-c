from pydantic import BaseModel
from datetime import datetime
from typing import Any


class TriggerRequest(BaseModel):
    file_path: str | None = None
    file_id: int | None = None
    owner_id: int | None = None


class RerunRequest(BaseModel):
    layer: str


class CatalogResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    mime_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    enable_vector: bool = True
    enable_bm25: bool = True
    enable_label: bool = True
    enable_dict: bool = True
    enable_graph: bool = True
    enable_rerank: bool = True
    enable_ppr: bool = True
    weights: dict[str, float] | None = None


class ScoreDetail(BaseModel):
    vector: float = 0.0
    bm25: float = 0.0
    label: float = 0.0
    dict_score: float = 0.0
    graph: float = 0.0
    freshness: float = 0.0
    combined: float = 0.0
    rerank_score: float | None = None
    ppr_score: float | None = None


class LightweightIndex(BaseModel):
    recall_type: str
    source_id: int
    catalog_id: int
    page_num: int | None = None
    summary: str | None = None
    subject: str | None = None
    attribute_hints: list[dict[str, str]] | None = None
    labels: list[str] | None = None
    graph_neighbors: list[dict[str, Any]] | None = None
    evidence_types: list[str] | None = None
    scores: ScoreDetail | None = None
    fusion_text_preview: str | None = None
    deep_read_url: str | None = None
    source_url: str | None = None


class SearchResult(BaseModel):
    items: list[LightweightIndex]
    total: int
    query: str
    recall_used: list[str]
    rerank_used: bool
    ppr_used: bool


class PageFusionRequest(BaseModel):
    fusion_id: int | None = None
    catalog_id: int | None = None
    page_num: int | None = None
    offset: int = 0
    limit: int = 2000


class EvidenceSource(BaseModel):
    source_type: str
    content: str | None = None
    screenshot_md5: str | None = None


class EvidenceBindConclusionRequest(BaseModel):
    conclusions: list[str]
    note: str = ""


class PageFusionResult(BaseModel):
    fusion_id: int
    catalog_id: int
    page_num: int
    file_name: str | None = None
    fusion_text: str | None = None
    summary: str | None = None
    attributes: dict | None = None
    labels: dict | None = None
    evidence: dict | None = None
    conflicts: dict | None = None
    quality_score: float | None = None
    original_sources: list[EvidenceSource] | None = None


class CandidateDecisionRequest(BaseModel):
    candidate_id: int
    reason: str = ""
    target_entity_id: int | None = None


class EntityCreateRequest(BaseModel):
    standard_name: str
    entity_type: str
    confirm_status: str = "confirmed"


class EntityUpdateRequest(BaseModel):
    standard_name: str | None = None
    entity_type: str | None = None
    confirm_status: str | None = None


class EntityAliasCreateRequest(BaseModel):
    entity_id: int
    alias: str
    alias_type: str = "synonym"


class EntityMergeRequest(BaseModel):
    from_entity_id: int
    to_entity_id: int
    reason: str = "manual merge"
