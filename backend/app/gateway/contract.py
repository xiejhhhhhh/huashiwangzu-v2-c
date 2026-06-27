from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ToolCall:
    id: str = ""
    type: str = "function"
    function: dict = field(default_factory=dict)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ModelRequest:
    messages: list[dict]
    system_prompt: str | None = None
    tools: list[dict] | None = None
    stream: bool = False
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 4096
    response_format: dict | None = None


@dataclass
class ModelResponse:
    content: str = ""
    thinking: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Usage | None = None
    error: str | None = None


class StreamEventType:
    TOKEN = "token"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    DONE = "done"
    ERROR = "error"


@dataclass
class StreamEvent:
    type: str
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    usage: Usage | None = None


def model_request_from_dict(d: dict) -> ModelRequest:
    return ModelRequest(
        messages=d.get("messages", []),
        system_prompt=d.get("system_prompt"),
        tools=d.get("tools"),
        stream=d.get("stream", False),
        temperature=d.get("temperature", 0.7),
        top_p=d.get("top_p", 1.0),
        max_tokens=d.get("max_tokens", 4096),
        response_format=d.get("response_format"),
    )


def model_response_to_dict(r: ModelResponse) -> dict:
    result: dict = {
        "content": r.content,
        "thinking": r.thinking,
        "tool_calls": [asdict(tc) for tc in r.tool_calls],
        "finish_reason": r.finish_reason,
    }
    if r.usage:
        result["usage"] = asdict(r.usage)
    if r.error:
        result["error"] = r.error
    return result


def stream_event_to_dict(e: StreamEvent) -> dict:
    result: dict = {"type": e.type, "content": e.content}
    if e.tool_calls:
        result["tool_calls"] = [asdict(tc) for tc in e.tool_calls]
    if e.usage:
        result["usage"] = asdict(e.usage)
    return result


def build_model_request(
    messages: list[dict],
    system_prompt: str | None = None,
    tools: list[dict] | None = None,
    stream: bool = False,
    temperature: float = 0.7,
    top_p: float = 1.0,
    max_tokens: int = 4096,
    response_format: dict | None = None,
) -> ModelRequest:
    return ModelRequest(
        messages=messages,
        system_prompt=system_prompt,
        tools=tools,
        stream=stream,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        response_format=response_format,
    )
