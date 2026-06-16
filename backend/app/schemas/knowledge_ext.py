from pydantic import BaseModel, Field
from typing import Literal


class LlmEntityOutput(BaseModel):
    standard_name: str = Field(..., min_length=1, max_length=256)
    entity_type: Literal[
        "brand", "product", "kit", "ingredient", "efficacy",
        "organization", "doc_type", "member_plan", "training_system",
    ]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=512)
    is_new: bool = Field(default=False, description="Not in known dictionary, should only go to candidates")


class LlmAttributeOutput(BaseModel):
    subject: str = Field(..., max_length=256)
    attr_name: str = Field(..., max_length=128)
    attr_value: str = Field(..., max_length=1024)
    source_page: int | None = None
    evidence: str = Field(default="", max_length=2048)


class LlmBatchResult(BaseModel):
    entities: list[LlmEntityOutput] = Field(default_factory=list)
    attributes: list[LlmAttributeOutput] = Field(default_factory=list)
    to_ignore: list[str] = Field(default_factory=list)


class CandidateVerdict(BaseModel):
    candidate_id: int
    verdict: Literal["pending", "confirmed", "ignored", "archived"]
    reason: str = ""
    target_entity_id: int | None = None
