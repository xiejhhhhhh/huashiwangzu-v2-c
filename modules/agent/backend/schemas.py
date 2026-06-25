from pydantic import BaseModel


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


class UpdatePromptRequest(BaseModel):
    content: str


class ApprovalDecision(BaseModel):
    decision: str
    reason: str | None = None


class PromptItemCreate(BaseModel):
    title: str
    category: str
    content: str
    is_active: bool = True
    status: str = "draft"


class PromptItemUpdate(BaseModel):
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
