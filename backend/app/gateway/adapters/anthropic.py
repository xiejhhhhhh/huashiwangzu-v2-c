"""ant 协议(Anthropic /v1/messages)适配器。

按 2026-07-16 探针实测的真实形状 1:1 归一,不猜:
- 非流式响应: content[] 是块数组,{"type":"thinking",...} 在前,{"type":"text","text":...} 在后
- 流式 SSE 事件: message_start / content_block_start / content_block_delta
  (thinking_delta | text_delta) / content_block_stop / message_delta / message_stop
- usage: input_tokens / output_tokens(_extract_usage 已兼容)

服务商差异(deepseek官方带thinking块+service_tier;jayce中转站只text)都在
content[] 遍历里自然消化,归一成统一 {content, thinking, tool_calls}。
前端一套模板通吃,不用管后端选了哪个 ant 服务商。
"""
from app.gateway.contract import ModelResponse, StreamEvent, StreamEventType

from .base import (
    ModelAdapter,
    _build_stream_event,
    _build_unified,
    _extract_usage,
)


class AnthropicAdapter(ModelAdapter):
    include_thinking = True

    def adapt_response(self, raw: dict, provider: str = "") -> ModelResponse:
        usage = _extract_usage(raw)
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in raw.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and block.get("text") is not None:
                content_parts.append(str(block["text"]))
            elif btype == "thinking" and self.include_thinking and block.get("thinking"):
                thinking_parts.append(str(block["thinking"]))
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("input") or {},
                    },
                })
        # ant 用 stop_reason: end_turn/max_tokens/tool_use/stop_sequence
        stop_reason = raw.get("stop_reason") or "stop"
        finish_reason = "tool_calls" if stop_reason == "tool_use" else "stop"
        return _build_unified(
            content="".join(content_parts),
            thinking="\n".join(p for p in thinking_parts if p),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
        )

    def adapt_stream_chunk(self, chunk: dict, provider: str = "") -> StreamEvent | None:
        etype = chunk.get("type")
        if etype == "content_block_delta":
            delta = chunk.get("delta") or {}
            dtype = delta.get("type")
            if dtype == "text_delta" and delta.get("text"):
                return _build_stream_event(StreamEventType.TOKEN, str(delta["text"]))
            if dtype == "thinking_delta" and self.include_thinking and delta.get("thinking"):
                return _build_stream_event(StreamEventType.THINKING, str(delta["thinking"]))
            # input_json_delta(tool_use 参数增量)累积交给上层,这里跳过
            return None
        if etype in {"message_delta", "message_stop"}:
            # ant 用量在 message_delta 里(output_tokens全量),结束信号是 message_stop
            # 两者都归一成 DONE 带 usage,前端一套模板收尾
            usage = _extract_usage(chunk)
            return _build_stream_event(StreamEventType.DONE, usage=usage)
        if etype == "error":
            err = chunk.get("error") or {}
            return _build_stream_event(
                StreamEventType.ERROR,
                str(err.get("message") or err or "anthropic stream error"),
            )
        # message_start / content_block_start / content_block_stop / ping: 结构事件,跳过
        return None
