from pydantic import BaseModel, Field


class CreateConvRequest(BaseModel):
    title: str = "新对话"


class RenameConvRequest(BaseModel):
    title: str


class ChatRequest(BaseModel):
    conversation_id: int
    content: str
    profile_key: str | None = None
    resume_checkpoint_id: str | None = None
    enable_checkpointer: bool | None = None


class EditResubmitRequest(BaseModel):
    content: str
    profile_key: str | None = None


class UpdatePromptRequest(BaseModel):
    content: str


class ApprovalDecision(BaseModel):
    decision: str
    reason: str | None = None
    payload_hash: str | None = None


class WorkflowCreateRequest(BaseModel):
    title: str
    intent: str = ""
    source: str = "manual"
    owner_id: int | None = None
    extra_meta: dict = Field(default_factory=dict)


class WorkflowStepRequest(BaseModel):
    step_key: str
    title: str
    type: str = "agent"
    status: str | None = None
    order_index: int | None = None
    input_ref: dict | None = None
    output_ref: dict | None = None
    max_retries: int = 0
    summary: str | None = None
    extra_meta: dict = Field(default_factory=dict)


class WorkflowToolCallRequest(BaseModel):
    run_id: int | None = None
    step_id: int | None = None
    tool_name: str
    target_module: str | None = None
    action: str | None = None
    caller: str | None = None
    arguments: dict | list | str | int | float | bool | None = None
    side_effect_level: str = "readonly"
    approval_policy: str = "auto"
    status: str = "planned"
    idempotency_key: str | None = None
    agent_run_id: str | None = None
    extra_meta: dict = Field(default_factory=dict)


class WorkflowArtifactRequest(BaseModel):
    run_id: int | None = None
    step_id: int | None = None
    artifact_type: str
    storage_kind: str
    storage_ref: dict | str | None = None
    visibility: str = "user"
    lifecycle: str = "candidate"
    ttl_seconds: int | None = None
    checksum: str | None = None
    summary: str | None = None
    extra_meta: dict = Field(default_factory=dict)


class WorkflowVerificationRequest(BaseModel):
    run_id: int | None = None
    step_id: int | None = None
    verification_type: str
    status: str
    command_or_capability: str | None = None
    evidence_ref: dict | None = None
    summary: str | None = None
    is_required_for_completion: bool = True
    duration_ms: int | None = None
    extra_meta: dict = Field(default_factory=dict)


class WorkflowApprovalRequest(BaseModel):
    run_id: int | None = None
    tool_call_id: int
    agent_code: str = "default"
    reason: str | None = None
    request_type: str = "tool_call"
    risk_level: str = "dangerous"
    decision_scope: str = "single_call"
    resume_target: dict | None = None


class WorkflowFinalizeRequest(BaseModel):
    developer_summary: str | None = None


class WorkflowCancelRequest(BaseModel):
    reason: str | None = None


class PromptItemCreate(BaseModel):
    key: str = ""
    title: str
    category: str
    content: str
    is_active: bool = True
    status: str = "draft"


class PromptItemUpdate(BaseModel):
    key: str | None = None
    title: str | None = None
    category: str | None = None
    content: str | None = None
    is_active: bool | None = None
    status: str | None = None


class AgentConfigCreate(BaseModel):
    agent_code: str
    agent_name: str = ""
    provider: str = ""
    model: str = ""
    system_prompt: str = ""
    purpose: str = ""
    enabled: bool = True
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_ms: int | None = None
    fallback_model: str | None = None
    fallback_enabled: bool = False
    max_concurrency: int | None = None
    cooldown_seconds: int | None = None
    retry_count: int = 3
    daily_call_limit: int | None = None
    daily_budget: float | None = None
    monthly_budget: float | None = None
    response_format: str = "text"
    log_prompt_enabled: bool = True
    log_response_enabled: bool = True
    sensitive_action_policy: str = "confirm"


class AgentConfigUpdate(BaseModel):
    agent_name: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    purpose: str | None = None
    enabled: bool | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_ms: int | None = None
    fallback_model: str | None = None
    fallback_enabled: bool | None = None
    max_concurrency: int | None = None
    cooldown_seconds: int | None = None
    retry_count: int | None = None
    daily_call_limit: int | None = None
    daily_budget: float | None = None
    monthly_budget: float | None = None
    response_format: str | None = None
    log_prompt_enabled: bool | None = None
    log_response_enabled: bool | None = None
    sensitive_action_policy: str | None = None
