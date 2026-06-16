import json


def extract_stream_payload(line: str) -> str | None:
    text = line.strip()
    if not text or text.startswith(":") or text.startswith("event:"):
        return None
    if text.startswith("data:"):
        return text[5:].strip()
    if text.startswith("{") or text.startswith("["):
        return text
    return None


def format_error(error: object) -> str:
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error") or error)
    return str(error)


def error_message(status_code: int, body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
        detail = format_error(payload.get("error") or payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        detail = body.decode("utf-8", errors="ignore")[:200]
    if status_code in (401, 403):
        return "云端鉴权失败，请检查 DeepSeek/OpenCode Go 密钥"
    if status_code == 429:
        return "云端请求过于频繁，请稍后再试"
    return detail or f"AI 云端模型暂时连不上，状态码 {status_code}"
