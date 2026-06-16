import httpx
import time

from app.config import get_settings

DEFAULT_MODEL = "deepseek-v4-flash"
MIMO_BASE = "https://opencode.ai/zen/go/v1"


def build_prompt(
    system_template: str,
    user_input: str,
    confirmed_entities: list[str] | None = None,
) -> tuple[str, str]:
    if not confirmed_entities:
        return system_template, user_input
    entity_list = "\n".join(f"  - {entity}" for entity in confirmed_entities)
    system_prompt = (
        f"{system_template}\n\n"
        f"【已确认词典 - 只能从以下实体中选择，新发现只能输出为候选】\n"
        f"{entity_list}\n"
    )
    return system_prompt, user_input


async def mimo_chat(
    system_prompt: str,
    user_input: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    settings = get_settings()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{MIMO_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def call_llm_raw(
    system_prompt: str,
    user_input: str,
    model: str = DEFAULT_MODEL,
) -> tuple[str, float]:
    started_at = time.time()
    raw = await mimo_chat(system_prompt, user_input, model=model)
    duration_ms = int((time.time() - started_at) * 1000)
    return raw, duration_ms
