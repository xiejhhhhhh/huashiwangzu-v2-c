# 工具调用格式结论 · deepseek-v4-flash（经 opencode-go）

> 实测时间：2025-06-22
> 探针：`modules/agent/tools/probe_toolcall_format.py`
> 落盘：`modules/agent/调研/工具调用格式探针_原始返回.jsonl`

## 一句话结论

deepseek-v4-flash 经 opencode-go 返回**标准 OpenAI-compatible 格式**，tool_calls 在
`choices[0].message.tool_calls` 数组中，`arguments` 为 JSON 字符串。**适配器（DeepSeekAdapter）
此前未提取 tool_calls，这是泄漏和反应式补丁的根因。**

## 实测格式

### 非流式返回结构

```json
{
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "",
      "tool_calls": [
        {
          "id": "call_00_...",
          "type": "function",
          "function": {
            "name": "get_weather",
            "arguments": "{\"city\": \"北京\", \"unit\": \"celsius\"}"
          }
        }
      ],
      "reasoning_content": "(思考过程，可选)"
    },
    "finish_reason": "tool_calls"
  }]
}
```

### 关键结论

| 维度 | 结论 |
|------|------|
| tool_calls 位置 | `choices[0].message.tool_calls`（标准） |
| arguments 类型 | JSON **字符串**（需 parse） |
| 中文编码 | UTF-8 正常 |
| 并行多工具 | 同一 `tool_calls` 数组多个元素（3 个全通过） |
| content 与 tool_calls 共存 | 可以同时有 content 和 tool_calls |
| finish_reason | 有工具时 `"tool_calls"`，无工具时 `"stop"` |
| tool_choice | 默认 `"auto"`，不传即 auto |
| 多轮一致性 | 工具结果喂回后，第二轮正常 |

### 并行格式

```json
{
  "tool_calls": [
    {"id": "call_00_...", "function": {"name": "get_weather", "arguments": "{\"city\": \"北京\"}"}},
    {"id": "call_01_...", "function": {"name": "get_time", "arguments": "{\"city\": \"东京\"}"}},
    {"id": "call_02_...", "function": {"name": "get_air_quality", "arguments": "{\"city\": \"上海\"}"}}
  ]
}
```

并行 = 一个 tool_calls 数组包含多个元素。不是内联重复块，不是正文 invoke。

### 流式

deepseek-v4-flash 经 opencode-go 的流式响应中：
- 思考过程走 `reasoning_content`（映射为 `thinking` 事件）
- **tool_calls 不在 SSE delta 中发出**（流式无工具调用能力）
- 工具调用必须走非流式路径

这意味着当前 `_yield_final_stream`（流式收尾）正常情况下不会遇到 tool_calls。
但保留了 `parse_inline_tool_calls` 作为兜底，以防模型在流式 content 正文中塞入
`<invoke>` 标记（极低概率）。

## 之前的问题

**根因**：`backend/app/gateway/adapters/deepseek.py` 的 `adapt_response` 和
`adapt_stream_chunk` 未调用 `_extract_openai_tool_calls`，导致 tool_calls 从
返回中被丢弃。agent 模块的 `model_client.py` 用 `recover_tool_calls`（重发一次请求）
和 `parse_inline_tool_calls`（正则从正文猜 XML）来补救 → 耗 API、易泄漏、反应式。

## 修复

1. **DeepSeekAdapter.adapt_response** — 添加 `_extract_openai_tool_calls(choice)`，
   结果传 `_build_unified` 的 tool_calls 参数。
2. **DeepSeekAdapter.adapt_stream_chunk** — 添加 delta.tool_calls 检测 + `_extract_delta_tool_calls`。
3. **model_client.py** — 精简为正则兜底，标记适配器已修对，`recover_tool_calls` 几乎不再被触发。
4. **router.py** — 并行工具执行（asyncio.gather + Semaphore(5)）。

## 所有观察到的变体（模板兼容全集）

1. 标准 `message.tool_calls` 数组 ✅（100% 走这个）
2. arguments 为 JSON 字符串 ✅（当前生产行为）
3. 空 content + tool_calls ✅
4. 有 content + tool_calls ✅（部分模型会先写句人话再调工具）
5. finish_reason 为 `"tool_calls"` ✅
6. 无工具时 finish_reason 为 `"stop"` ✅
7. reasoning_content 携带思考过程 ✅
