"""
Chat Service - 채팅 로직, Redis Queue Producer, 스트리밍, ChatHistory 저장
Agentic 라우팅 실행 → 데이터 수집 → LLM 최종 답변 스트리밍 → DB 저장.
"""
import asyncio
import json
import logging
from typing import Any, AsyncGenerator
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_redis
from app.models import ChatHistory
from app.services.graph_service import search_herb_graph
from app.services.llm_router import analyze_intent
from app.services.sql_worker import SQL_RESULT_PREFIX, SQL_TASK_QUEUE
from app.utils.prompts import (
    FINAL_ANSWER_SYSTEM_PROMPT,
    FINAL_ANSWER_USER_TEMPLATE,
    TEXT_TO_SQL_SYSTEM_PROMPT,
    TEXT_TO_SQL_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)
settings = get_settings()


async def _call_llm_stream(
    system_prompt: str,
    user_content: str,
    send_fn: Any,
) -> str:
    """
    LLM 스트리밍 호출. send_fn(type, content)로 토큰 전송.
    Mock 모드: asyncio.sleep + 전체 답변 한 글자씩 스트리밍.
    """
    full_response = ""

    if settings.USE_MOCK_LLM or not settings.OPENAI_API_KEY:
        await asyncio.sleep(0.3)
        full_response = "안녕하세요. 팔란티니 한약재 챗봇입니다. 문의해 주셔서 감사합니다. 추가로 궁금하신 점이 있으시면 말씀해 주세요."
        for ch in full_response:
            await send_fn("token", ch)
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
                await send_fn("token", token)
        return full_response
    except Exception as e:
        logger.exception("LLM stream error: %s", e)
        fallback = "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        for ch in fallback:
            await send_fn("token", ch)
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
    # SQL 정제 (주석 제거 등)
    sql = sql.split("--")[0].strip()
    if not sql.upper().startswith("SELECT"):
        return "재고/단가 조회는 SELECT 쿼리만 가능합니다."

    task_id = str(uuid4())
    result_key = f"{SQL_RESULT_PREFIX}{task_id}"
    task_payload = json.dumps({"task_id": task_id, "sql": sql, "result_key": result_key}, ensure_ascii=False)

    await redis.lpush(SQL_TASK_QUEUE, task_payload)

    # BLPOP으로 결과 대기 (타임아웃 30초)
    result = await redis.blpop(result_key, timeout=30)
    if result is None:
        return "DB 조회 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."

    _, data_str = result
    data = json.loads(data_str)
    if isinstance(data, dict) and "error" in data:
        return f"조회 중 오류: {data['error']}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get_recent_history(db: AsyncSession, user_id: str, session_id: str, limit: int = 10) -> str:
    """최근 대화를 문자열로 반환 (LLM 컨텍스트용)."""
    result = await db.execute(
        select(ChatHistory)
        .where((ChatHistory.user_id == user_id) | (ChatHistory.session_id == session_id))
        .order_by(desc(ChatHistory.created_at))
        .limit(limit * 2)  # user+assistant 쌍
    )
    rows = result.scalars().all()
    lines = [f"{r.role}: {r.content}" for r in reversed(rows)]
    return "\n".join(lines) if lines else "(이전 대화 없음)"


async def process_message(
    db: AsyncSession,
    redis: Redis,
    session_id: str,
    user_id: str,
    message: str,
    send_fn: Any,
) -> None:
    """
    채팅 메시지 처리 전체 플로우.
    1. status(의도분석) → 2. 라우팅 실행 → 3. 데이터 수집 → 4. 스트리밍 → 5. end → 6. ChatHistory 저장
    """

    async def send(type: str, content: str = "") -> None:
        payload = {"type": type, "content": content}
        await send_fn(payload)

    # 1. 의도 분석
    await send("status", "질문 의도 분석 중...")
    routing = await analyze_intent(message)
    route = routing.get("route", "GENERAL")
    extracted = routing.get("extracted_entities", {})

    # 2. 라우트별 데이터 수집
    context = ""
    if route == "GRAPH":
        await send("status", "한약재 지식 그래프 탐색 중...")
        context = await search_herb_graph(message, extracted)
    elif route == "DB_SQL":
        await send("status", "DB 접근을 위한 Text-to-SQL 작업 중...")
        context = await _execute_sql_via_redis(message, redis)
    else:
        await send("status", "이전 대화 맥락 확인 중...")
        context = ""

    history_str = await get_recent_history(db, user_id, session_id)
    user_content = FINAL_ANSWER_USER_TEMPLATE.format(
        context=context,
        history=history_str,
        message=message,
    )

    # 3. 최종 답변 스트리밍
    full_response = await _call_llm_stream(FINAL_ANSWER_SYSTEM_PROMPT, user_content, send)

    # 4. 종료 신호
    await send("end")

    # 5. ChatHistory 저장
    user_msg = ChatHistory(session_id=session_id, user_id=user_id, role="user", content=message)
    assistant_msg = ChatHistory(session_id=session_id, user_id=user_id, role="assistant", content=full_response)
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()
