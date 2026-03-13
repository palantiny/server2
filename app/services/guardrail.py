"""
Guardrail - 라우트 결과 사전 검증 (Pre-validation)
LLM 호출 전에 라우트 결과를 검증하여 빈 결과, SQL 에러, 비정상 데이터를 걸러냄.
Mock 모드에서는 규칙 기반 검증만 수행.
"""
import json
import logging
from typing import Any

from app.core.config import get_settings
from app.utils.prompts import GUARDRAIL_SYSTEM_PROMPT, GUARDRAIL_USER_TEMPLATE

logger = logging.getLogger(__name__)
settings = get_settings()

# 규칙 기반 에러 패턴
_ERROR_PATTERNS = [
    "error", "오류", "실패", "exception", "traceback",
    "syntax error", "permission denied", "timeout",
]


def _rule_based_check(route: str, context: str) -> tuple[bool, str]:
    """규칙 기반 검증. (valid, reason) 반환."""
    if not context or not context.strip():
        return False, f"{route}: 결과가 비어있음"

    lower = context.lower()
    for pattern in _ERROR_PATTERNS:
        if pattern in lower and len(context) < 200:
            return False, f"{route}: 에러 패턴 감지 ({pattern})"

    return True, ""


async def validate_context(
    route_results: list[tuple[str, str]],
    message: str,
) -> dict[str, Any]:
    """
    라우트 결과를 순회하며 검증.

    반환:
        {
            "validated_context": str,  # 검증 통과한 결과만 포맷팅
            "warnings": list[str],     # 경고 메시지 목록
            "dropped_routes": list[str] # 제거된 라우트 이름
        }
    """
    validated: list[tuple[str, str]] = []
    warnings: list[str] = []
    dropped: list[str] = []

    for route, context in route_results:
        valid, reason = _rule_based_check(route, context)

        if not valid:
            dropped.append(route)
            warnings.append(reason)
            logger.info("Guardrail dropped route %s: %s", route, reason)
            continue

        if not settings.USE_MOCK_LLM and settings.OPENAI_API_KEY:
            llm_valid = await _llm_validate(route, context, message)
            if not llm_valid:
                dropped.append(route)
                warnings.append(f"{route}: LLM 검증 실패 (질문과 무관한 데이터)")
                logger.info("Guardrail LLM dropped route %s", route)
                continue

        validated.append((route, context))

    # 검증 통과한 결과를 포맷팅
    from app.services.chat_service import ROUTE_LABELS

    blocks: list[str] = []
    for route, ctx in validated:
        label = ROUTE_LABELS.get(route, route)
        blocks.append(f"--- {label} 결과 ---\n{ctx}")

    return {
        "validated_context": "\n\n".join(blocks),
        "warnings": warnings,
        "dropped_routes": dropped,
    }


async def _llm_validate(route: str, context: str, message: str) -> bool:
    """LLM 기반 검증. 실패 시 True 반환 (통과 처리)."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        user_content = GUARDRAIL_USER_TEMPLATE.format(
            message=message, route=route, context=context[:2000],
        )
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": GUARDRAIL_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        text = (response.choices[0].message.content or "").strip()
        result = json.loads(text)
        return result.get("valid", True)
    except Exception as e:
        logger.warning("Guardrail LLM validation error: %s", e)
        return True
