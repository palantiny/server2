"""
LLM 라우터 - 의도 분석 및 Agentic 라우팅
사용자 메시지를 분석하여 GRAPH/DB_SQL/GENERAL 중 하나로 분기.
Mock 모드: API 키 없을 때 asyncio.sleep + 고정 응답으로 전환.
"""
import asyncio
import json
import re
from typing import Any

from app.core.config import get_settings
from app.utils.prompts import ROUTING_SYSTEM_PROMPT, ROUTING_USER_TEMPLATE

settings = get_settings()

# Mock 모드에서 의도 기반 라우팅을 위한 키워드 매칭 (LLM 대체)
MOCK_ROUTING_KEYWORDS = {
    "GRAPH": ["효능", "원산지", "관계", "궁합", "어떤", "무슨", "뭐", "감초", "대추", "인삼", "생강"],
    "DB_SQL": ["재고", "단가", "가격", "수량", "얼마", "있어", "남아", "입고", "출고"],
}


def _mock_route_by_keywords(message: str) -> dict[str, Any]:
    """Mock: 키워드 기반 라우팅."""
    msg_lower = message.strip().lower()
    for route, keywords in MOCK_ROUTING_KEYWORDS.items():
        if any(kw in message or kw in msg_lower for kw in keywords):
            return {
                "route": route,
                "reason": f"Mock keyword match: {route}",
                "extracted_entities": {"herb_name": _extract_herb_from_message(message)},
            }
    return {
        "route": "GENERAL",
        "reason": "Mock default",
        "extracted_entities": {},
    }


def _extract_herb_from_message(message: str) -> str | None:
    """메시지에서 한약재명 추출 (간단한 휴리스틱)."""
    herbs = ["감초", "대추", "생강", "인삼", "황기", "당귀", "계피"]
    for h in herbs:
        if h in message:
            return h
    return None


def _parse_routing_json(text: str) -> dict[str, Any] | None:
    """LLM 출력에서 JSON 파싱."""
    # JSON 블록 추출
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


async def analyze_intent(message: str) -> dict[str, Any]:
    """
    사용자 메시지 의도 분석.
    반환: {"route": "GRAPH|DB_SQL|GENERAL", "reason": "...", "extracted_entities": {...}}
    """
    # Mock 모드: API 키 없거나 USE_MOCK_LLM=True
    if settings.USE_MOCK_LLM or not settings.OPENAI_API_KEY:
        await asyncio.sleep(0.5)  # 지연 시뮬레이션
        return _mock_route_by_keywords(message)

    # 실제 OpenAI 호출
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
                {"role": "user", "content": ROUTING_USER_TEMPLATE.format(message=message)},
            ],
            temperature=0.1,
        )
        text = response.choices[0].message.content or ""
        parsed = _parse_routing_json(text)
        if parsed and "route" in parsed:
            route = parsed["route"].upper()
            if route not in ("GRAPH", "DB_SQL", "GENERAL"):
                route = "GENERAL"
            return {
                "route": route,
                "reason": parsed.get("reason", ""),
                "extracted_entities": parsed.get("extracted_entities", {}),
            }
    except Exception:
        pass

    # 실패 시 Mock 폴백
    return _mock_route_by_keywords(message)
