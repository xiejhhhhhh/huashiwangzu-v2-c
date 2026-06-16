from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def parse_json(text: str) -> dict | list | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\[[\s\S]*?\]", r"\{[\s\S]*?\}"):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def validate_with_pydantic(
    data: dict | list,
    schema: type[T],
) -> tuple[T | None, str | None]:
    try:
        if isinstance(data, list):
            return None, f"Expected a single object but got a list for {schema.__name__}"
        return schema.model_validate(data), None
    except Exception as exc:
        return None, str(exc)
