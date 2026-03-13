"""
Chat Service - 채팅 로직, Redis Pub/Sub 퍼블리셔, 스트리밍, ChatHistory 저장
Agentic 라우팅 실행 → 데이터 수집 → Guardrail 검증 → LLM 최종 답변 스트리밍 → MongoDB 저장.
Adaptive Fan-out: 복합 질문 시 여러 라우트를 병렬 실행 후 결과 합성.

send_fn 대신 redis.publish()로 SSE 이벤트를 전송.
"""
import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.graph_service import search_herb_graph
from app.services.guardrail import validate_context
from app.services.history_manager import get_context_within_limit
from app.services.llm_router import analyze_intent
from app.services.sql_worker import SQL_RESULT_PREFIX, SQL_TASK_QUEUE
from app.utils.prompts import (
    FINAL_ANSWER_SYSTEM_PROMPT,
    FINAL_ANSWER_USER_TEMPLATE,
    SYNTHESIZER_SYSTEM_PROMPT,
    SYNTHESIZER_USER_TEMPLATE,
    TEXT_TO_SQL_SYSTEM_PROMPT,
    TEXT_TO_SQL_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def _publish_event(redis: Redis, channel: str, event_type: str, content: str = "") -> None:
    """Redis Pub/Sub로 SSE 이벤트 발행."""
    payload = json.dumps({"type": event_type, "content": content}, ensure_ascii=False)
    await redis.publish(channel, payload)


async def _call_llm_stream(
    system_prompt: str,
    user_content: str,
    redis: Redis,
    channel: str,
) -> str:
    """
    LLM 스트리밍 호출. redis.publish()로 토큰 전송.
    Mock 모드: asyncio.sleep + 전체 답변 한 글자씩 스트리밍.
    """
    full_response = ""

    if settings.USE_MOCK_LLM or not settings.OPENAI_API_KEY:
        await asyncio.sleep(0.3)
        full_response = "안녕하세요. 팔란티니 한약재 챗봇입니다. 문의해 주셔서 감사합니다. 추가로 궁금하신 점이 있으시면 말씀해 주세요."
        for ch in full_response:
            await _publish_event(redis, channel, "token", ch)
            await asyncio.sleep(0.02)
        return full_response

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=True,
            temperature=0.7,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                await _publish_event(redis, channel, "token", token)
        return full_response
    except Exception as e:
        logger.exception("LLM stream error: %s", e)
        fallback = "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        for ch in fallback:
            await _publish_event(redis, channel, "token", ch)
        return fallback


async def _call_llm_text(system_prompt: str, user_content: str) -> str:
    """LLM 비스트리밍 호출 (Text-to-SQL 등)."""
    if settings.USE_MOCK_LLM or not settings.OPENAI_API_KEY:
        await asyncio.sleep(0.3)
        return "SELECT * FROM inventory LIMIT 5"

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.exception("LLM text error: %s", e)
        return "SELECT * FROM inventory LIMIT 5"


async def _execute_sql_via_redis(message: str, redis: Redis) -> str:
    """
    Redis Queue를 통한 Text-to-SQL 실행.
    DB 락 방지: Chat Service는 Producer로 LPUSH, Worker가 BRPOP 후 실행.
    """
    sql = await _call_llm_text(TEXT_TO_SQL_SYSTEM_PROMPT, TEXT_TO_SQL_USER_TEMPLATE.format(message=message))
    sql = sql.split("--")[0].strip()
    if not sql.upper().startswith("SELECT"):
        return "재고/단가 조회는 SELECT 쿼리만 가능합니다."

    task_id = str(uuid4())
    result_key = f"{SQL_RESULT_PREFIX}{task_id}"
    task_payload = json.dumps({"task_id": task_id, "sql": sql, "result_key": result_key}, ensure_ascii=False)

    await redis.lpush(SQL_TASK_QUEUE, task_payload)

    result = await redis.blpop(result_key, timeout=30)
    if result is None:
        return "DB 조회 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."

    _, data_str = result
    data = json.loads(data_str)
    if isinstance(data, dict) and "error" in data:
        return f"조회 중 오류: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _get_herb_from_cache(redis: Redis, herb_name: str) -> str:
    """Redis 캐시에서 한약재 데이터 조회. 캐시 미스 시 빈 문자열."""
    try:
        key = f"herb:cache:{herb_name}"
        data = await redis.get(key)
        if data:
            return data
    except Exception:
        pass
    return ""


ROUTE_LABELS = {
    "GRAPH": "한약재 지식 그래프",
    "CACHE": "캐시 데이터",
    "DB_SQL": "DB 조회 결과",
}


async def _execute_route(
    route: str,
    message: str,
    extracted: dict[str, Any],
    redis: Redis,
) -> tuple[str, str]:
    """단일 라우트 실행 디스패처. (route, context) 튜플 반환. 실패 시 빈 컨텍스트."""
    try:
        if route == "GRAPH":
            ctx = await search_herb_graph(message, extracted)
        elif route == "CACHE":
            herb_name = extracted.get("herb_name") or ""
            for h in ["감초", "대추", "생강", "인삼"]:
                if h in message:
                    herb_name = h
                    break
            ctx = await _get_herb_from_cache(redis, herb_name)
            if not ctx:
                ctx = await search_herb_graph(message, extracted)
        elif route == "DB_SQL":
            ctx = await _execute_sql_via_redis(message, redis)
        else:
            ctx = ""
        return (route, ctx)
    except Exception as e:
        logger.warning("Route %s failed: %s", route, e)
        return (route, "")


def _format_multi_context(results: list[tuple[str, str]]) -> str:
    """복수 라우트 결과를 레이블 구분된 컨텍스트 블록으로 포맷. 빈 결과 스킵."""
    blocks: list[str] = []
    for route, ctx in results:
        if not ctx:
            continue
        label = ROUTE_LABELS.get(route, route)
        blocks.append(f"--- {label} 결과 ---\n{ctx}")
    return "\n\n".join(blocks)


async def process_message(
    chat_repo: Any,
    redis: Redis,
    session_id: str,
    user_id: str,
    message: str,
) -> None:
    """
    채팅 메시지 처리 전체 플로우 (MQ Worker에서 호출).
    send_fn 대신 redis.publish()로 SSE 이벤트 직접 발행.

    1. 의도분석 → routes 배열
    2. 분기: GENERAL 직행 / 단일 라우트 / 복수 라우트 병렬
    3. Guardrail 검증
    4. 프롬프트 선택 → 스트리밍 → end → MongoDB 저장
    """
    channel = f"{settings.CHAT_STREAM_PREFIX}{session_id}"

    async def publish(event_type: str, content: str = "") -> None:
        await _publish_event(redis, channel, event_type, content)

    # 1. 의도 분석
    await publish("status", "질문 의도 분석 중...")
    routing = await analyze_intent(message)
    routes = routing.get("routes", ["GENERAL"])
    extracted = routing.get("extracted_entities", {})

    # 2. 라우트별 데이터 수집
    route_results: list[tuple[str, str]] = []
    use_synthesizer = False

    if routes == ["GENERAL"]:
        await publish("status", "이전 대화 맥락 확인 중...")
    elif len(routes) == 1:
        route = routes[0]
        label = ROUTE_LABELS.get(route, route)
        await publish("status", f"{label} 탐색 중...")
        result = await _execute_route(route, message, extracted, redis)
        route_results.append(result)
    else:
        route_names = ", ".join(routes)
        await publish("status", f"복수 데이터 소스 병렬 조회 중... ({route_names})")
        tasks = [_execute_route(r, message, extracted, redis) for r in routes]
        results = await asyncio.gather(*tasks)
        route_results = list(results)
        use_synthesizer = True

    # 3. Guardrail 검증
    if route_results:
        await publish("status", "데이터 검증 중...")
        guard_result = await validate_context(route_results, message)
        context = guard_result["validated_context"]

        for warning in guard_result["warnings"]:
            await publish("status", f"⚠ {warning}")

        if not context and guard_result["dropped_routes"]:
            await publish("status", "유효한 데이터가 없어 일반 지식으로 답변합니다.")
    else:
        context = ""

    # 4. 대화 히스토리 조회
    history_str = await get_context_within_limit(
        chat_repo, user_id, session_id,
    )

    # 5. 프롬프트 선택 및 최종 답변 스트리밍
    if use_synthesizer and context:
        system_prompt = SYNTHESIZER_SYSTEM_PROMPT
        user_content = SYNTHESIZER_USER_TEMPLATE.format(
            context=context, history=history_str, message=message,
        )
    else:
        system_prompt = FINAL_ANSWER_SYSTEM_PROMPT
        user_content = FINAL_ANSWER_USER_TEMPLATE.format(
            context=context, history=history_str, message=message,
        )

    full_response = await _call_llm_stream(system_prompt, user_content, redis, channel)

    # 6. 종료 신호
    await publish("end")

    # 7. ChatHistory 저장 (MongoDB) — user message는 POST 시점에 이미 저장됨
    await chat_repo.save(session_id, user_id, "assistant", full_response)
