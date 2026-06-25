"""Platform Resource IR — unified expression for all resource types.

This file defines the skeleton for a platform-wide resource object layer.
Every resource in the system (prompt, knowledge source, document_ir, artifact,
workflow node, connector, capability binding) can be expressed as a
ResourceObject with a common shape, leaving formal hanging points for future
expansion without requiring a full resource graph today.

Design principles:
- A single ResourceObject type with a resource_type discriminator
- resource_ref is a stable pointer (id + type) used by workflow step I/O
- metadata dict allows future extension without schema changes
- No ORM backing yet — pure Pydantic contract, ready for DB migration later
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """All resource categories in the platform resource graph."""
    prompt = "prompt"
    knowledge_source = "knowledge_source"
    document_ir = "document_ir"
    artifact = "artifact"
    workflow_node = "workflow_node"
    connector = "connector"
    capability_binding = "capability_binding"
    run_record = "run_record"
    step_record = "step_record"
    definition = "definition"


class ResourceRef(BaseModel):
    """A stable pointer to any platform resource.

    Used by workflow step input/output references, event payloads,
    and cross-module data handoff.  This is the universal "point at
    something" contract.
    """
    id: int | str
    resource_type: ResourceType
    label: str = ""
    version: str | None = None


class ResourceMetadata(BaseModel):
    """Common metadata attached to every resource."""
    owner_id: int | None = None
    conversation_id: int | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    trace: str | None = None  # correlation id for run ledger linkage


class ResourceObject(BaseModel):
    """A unified resource object in the platform resource graph.

    Every resource in the system should be expressible through this
    shape.  ``resource_type`` discriminates the semantic category,
    ``content`` carries the type-specific payload, and ``metadata``
    holds cross-cutting concerns.

    This type is not yet persisted to a single table — the goal is
    to define the *contract* so that future code can target it.
    """
    id: int | str
    resource_type: ResourceType
    content: dict = Field(default_factory=dict)
    refs: list[ResourceRef] = Field(default_factory=list)
    metadata: ResourceMetadata = Field(default_factory=ResourceMetadata)

    model_config = {"extra": "allow"}


class ResourceBinding(BaseModel):
    """A connector / capability binding — describes how a resource
    is wired to a capability or external system."""
    resource_ref: ResourceRef
    capability: str
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class WorkflowNodeResource(ResourceObject):
    """A workflow node expressed as a platform resource."""
    node_type: str = "task"  # task | decision | fork | join | sub_workflow
    input_bindings: list[ResourceBinding] = Field(default_factory=list)
    output_bindings: list[ResourceBinding] = Field(default_factory=list)
