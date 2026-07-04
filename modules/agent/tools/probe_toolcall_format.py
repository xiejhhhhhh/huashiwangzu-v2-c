"""Probe script: test deepseek-v4-flash tool call format via gateway client.
Reuses existing gateway — no direct HTTP, no Cloudflare bypass needed.

Usage:
    cd /path/to/backend && .venv/bin/python ../modules/agent/tools/probe_toolcall_format.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure backend is importable
BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("APP_ENV", "development")

from app.gateway.router import gateway_router

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查某个城市的实时天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "查某个城市的当前时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                    "timezone": {"type": "string", "description": "时区"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_air_quality",
            "description": "查某个城市的空气质量",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                },
                "required": ["city"],
            },
        },
    },
]

RESULTS: list[dict] = []


def record(label: str, raw: dict, is_stream: bool = False):
    RESULTS.append({
        "label": label,
        "is_stream": is_stream,
        "finish_reason": raw.get("finish_reason", "?"),
        "content_length": len(raw.get("content", "") or ""),
        "tool_calls_count": len(raw.get("tool_calls") or []),
        "tool_calls": raw.get("tool_calls", []),
    })
    print(f"\n{'='*60}")
    print(f"[{label}] finish_reason={raw.get('finish_reason')} "
          f"tool_calls={len(raw.get('tool_calls') or [])} "
          f"content_len={len(raw.get('content', '') or '')}")
    for tc in (raw.get("tool_calls") or []):
        fn = tc.get("function", tc)
        print(f"  → id={tc.get('id','')[:20]} name={fn.get('name','')} "
              f"args_type={type(fn.get('arguments','')).__name__} "
              f"args={json.dumps(fn.get('arguments',''), ensure_ascii=False)[:100]}")
    if not raw.get("tool_calls"):
        print(f"  content_preview={str(raw.get('content',''))[:200]}")


async def probe_non_stream():
    print("\n\n========== PROBE: Non-streaming ==========")

    # 1. No tools — baseline
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "你好，请简单介绍一下你自己。"}],
    )
    record("无工具-基线", r)

    # 2. Single tool — Chinese
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "今天北京天气怎么样？"}],
        tools=TOOLS,
    )
    record("单工具-中文天气", r)

    # 3. Single tool — English
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "What time is it in Tokyo?"}],
        tools=TOOLS,
    )
    record("单工具-英文时间", r)

    # 4. Parallel tools (independent)
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "同时查北京天气、东京时间和上海空气质量"}],
        tools=TOOLS,
    )
    record("并行多工具", r)

    # 5. Complex args (nested/中文)
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "北京的天气怎么样，用摄氏度显示"}],
        tools=TOOLS,
    )
    record("复杂参数-中文值", r)

    # 6. Without tools but asking for tool
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "现在几点了？"}],
    )
    record("无工具-问时间", r)

    # 7. Multi-turn: first call with tool, feed result back, second call
    r1 = await gateway_router.chat(
        messages=[{"role": "user", "content": "北京天气怎么样？"}],
        tools=TOOLS,
    )
    record("多轮-第1轮", r1)
    if r1.get("tool_calls"):
        msgs = [
            {"role": "user", "content": "北京天气怎么样？"},
            {"role": "assistant", "content": r1.get("content", ""), "tool_calls": r1.get("tool_calls", [])},
            {"role": "tool", "tool_call_id": r1["tool_calls"][0].get("id", ""), "content": '{"temperature": 25, "condition": "晴"}'},
        ]
        r2 = await gateway_router.chat(messages=msgs, tools=TOOLS)
        record("多轮-第2轮(喂结果)", r2)

    # 8. Model hesitates / explains before tool
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "你能帮我查一下北京的天气吗？我想知道明天要不要带伞。"}],
        tools=TOOLS,
    )
    record("犹豫后调工具", r)

    # 9. model says no tool needed
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "你好"}],
        tools=TOOLS,
    )
    record("明确说不需要工具", r)

    # 10. text + tool_choice = "required"
    r = await gateway_router.chat(
        messages=[{"role": "user", "content": "帮我查一下天气和空气质量"}],
        tools=TOOLS,
    )
    record("tool_choice不传(auto)", r)


async def probe_stream():
    print("\n\n========== PROBE: Streaming ==========")

    # Stream without tools
    print("\n[流式-无工具]")
    async for evt in gateway_router.chat_stream(
        messages=[{"role": "user", "content": "用一句话介绍北京"}],
    ):
        et = evt.get("type")
        if et in ("token", "thinking"):
            pass  # just consume
        elif et == "done":
            print("  [DONE]")
        elif et == "error":
            print(f"  [ERROR] {evt.get('content')}")

    # Stream with tools
    print("\n[流式-有工具]")
    async for evt in gateway_router.chat_stream(
        messages=[{"role": "user", "content": "北京天气怎么样？"}],
        tools=TOOLS,
    ):
        et = evt.get("type")
        if et in ("token", "thinking"):
            print(f"  {et}: {evt.get('content','')[:40]}")
        elif et == "done":
            print("  [DONE]")
        elif "tool_calls" in evt:
            print(f"  tool_calls: {json.dumps(evt.get('tool_calls'), ensure_ascii=False)[:200]}")
        elif et == "error":
            print(f"  [ERROR] {evt.get('content')}")
        else:
            print(f"  ?unknown: {json.dumps(evt, ensure_ascii=False)[:100]}")

    # Stream parallel
    print("\n[流式-并行工具]")
    async for evt in gateway_router.chat_stream(
        messages=[{"role": "user", "content": "同时查北京天气和上海空气质量"}],
        tools=TOOLS,
    ):
        et = evt.get("type")
        if et in ("token", "thinking"):
            pass
        elif et == "done":
            print("  [DONE]")
        elif "tool_calls" in evt:
            print(f"  tool_calls: {json.dumps(evt.get('tool_calls'), ensure_ascii=False)[:200]}")
        elif et == "error":
            print(f"  [ERROR] {evt.get('content')}")


async def main():
    print("Probing deepseek-v4-flash tool call format...")
    try:
        await probe_non_stream()
    except Exception as e:
        print(f"Non-stream probe failed: {e}", file=sys.stderr)

    try:
        await probe_stream()
    except Exception as e:
        print(f"Stream probe failed: {e}", file=sys.stderr)

    # Save results
    out_path = Path(__file__).resolve().parent.parent / "research" / "tool_call_format_probe_raw.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in RESULTS:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"\n\nResults saved to {out_path}")
    print(f"Total probes: {len(RESULTS)}")

    # Summary
    has_tc = sum(1 for r in RESULTS if r["tool_calls_count"] > 0)
    print(f"Probes with tool_calls: {has_tc}/{len(RESULTS)}")
    for r in RESULTS:
        print(f"  [{r['label']}] finish={r['finish_reason']} tc={r['tool_calls_count']}")


if __name__ == "__main__":
    asyncio.run(main())
