"""
Controlled LLM service with Pydantic structured output, dictionary injection,
and mandatory audit logging (knowledge_llm_logs).
"""
import logging
import httpx
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge.llm.audit import log_llm_call
from app.services.knowledge.llm.client import DEFAULT_MODEL, build_prompt, call_llm_raw
from app.services.knowledge.llm.parsing import parse_json, validate_with_pydantic

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def call_llm_structured(
    db: AsyncSession,
    caller: str,
    system_template: str,
    user_input: str,
    schema: type[T],
    confirmed_entities: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> tuple[T | None, str | None]:
    system_prompt, user_msg = build_prompt(
        system_template, user_input, confirmed_entities
    )

    raw_response = None
    parse_ok = False
    result_data: dict | None = None
    error: str | None = None
    duration_ms = 0
    cost = 0.0
    validated: T | None = None
    schema_error: str | None = None

    try:
        raw_response, duration_ms = await call_llm_raw(
            system_prompt, user_msg, model=model
        )
        parsed = parse_json(raw_response)
        if parsed is None:
            error = "LLM returned unparseable JSON"
            logger.warning("%s: %s", caller, error)
        else:
            parse_ok = True
            result_data = parsed if isinstance(parsed, dict) else {"data": parsed}
            to_validate = parsed
            if isinstance(to_validate, list):
                if len(to_validate) == 1:
                    to_validate = to_validate[0]
                else:
                    error = "LLM returned a list but schema expects a single object"
                    logger.warning("%s: %s", caller, error)
                    parse_ok = False
            if parse_ok:
                validated, schema_error = validate_with_pydantic(to_validate, schema)
            if schema_error:
                error = f"Pydantic validation failed: {schema_error}"
                parse_ok = False
                logger.warning("%s: %s", caller, error)
    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code}: {e.response.text[:500]}"
        logger.error("%s: %s", caller, error)
    except httpx.TimeoutException:
        error = "LLM request timed out"
        logger.error("%s: %s", caller, error)
    except Exception as e:
        error = f"Unexpected error: {e}"
        logger.exception("%s", caller)

    try:
        await log_llm_call(
            db=db,
            caller=caller,
            model=model,
            system_prompt=system_prompt,
            user_input=user_msg,
            raw_response=raw_response,
            parse_ok=parse_ok,
            result=result_data,
            error=error,
            duration_ms=duration_ms,
            cost=cost,
        )
    except Exception as log_e:
        logger.warning("Failed to write LLM audit log: %s", log_e)

    return validated, error


class LlmService:
    @staticmethod
    async def classify_subject(
        db: AsyncSession,
        text: str,
        confirmed_entities: list[str] | None = None,
    ) -> tuple[list[dict], str | None]:
        from app.services.knowledge.fusion.subject import LLMSubjectOutput

        system = (
            "你是一个知识库主体识别助手。从页面文本中识别页面围绕哪些主体展开。\n"
            "仅输出严格 JSON（不包含 markdown 代码块包裹），格式：\n"
            '{"subjects": [{"subject_type": "品牌|产品|成分|功效|检测|备案|会员方案|培训|其他", '
            '"name": "主体名", "reason": "为什么是主体", "evidence_pages": [1], "confidence": 0.92}], '
            '"should_ignore": ["不应该进入主体的文本片段"]}'
        )

        validated, error = await call_llm_structured(
            db=db,
            caller="subject_discovery",
            system_template=system,
            user_input=text[:8000],
            schema=LLMSubjectOutput,
            confirmed_entities=confirmed_entities,
        )

        if validated:
            return [
                {"subject_type": s.subject_type.value, "name": s.name,
                 "reason": s.reason, "evidence_pages": s.evidence_pages,
                 "confidence": s.confidence, "source": "llm"}
                for s in validated.subjects
            ], None
        return [], error
