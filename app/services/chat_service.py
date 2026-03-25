"""
Chat Service - 3단계 순차 LLM 파이프라인 오케스트레이터
LangGraph 기반 파이프라인(pipeline.py) 실행 → SSE 스트리밍 → MongoDB 저장.

Stage 1: Text-to-Cypher & 1차 라우팅 (Graph DB)
Stage 2: Text-to-SQL & 2차 라우팅 (RDB/Redis)
Stage 3: 최종 합성 답변 (Synthesizer)
"""
import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings
from app.services.history_manager import get_context_within_limit
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)
settings = get_settings()


async def _publish_event(redis: Redis, channel: str, event_type: str, content: str = "") -> None:
    """Redis Pub/Sub로 SSE 이벤트 발행."""
    payload = json.dumps({"type": event_type, "content": content}, ensure_ascii=False)
    await redis.publish(channel, payload)


async def process_message(
    chat_repo: Any,
    redis: Redis,
    session_id: str,
    user_id: str,
    message: str,
) -> None:
    """
    채팅 메시지 처리 전체 플로우 (MQ Worker에서 호출).

    1. 대화 히스토리 조회 (128k 토큰 제한)
    2. LangGraph 3단계 파이프라인 실행
    3. 종료 신호 발행
    4. 어시스턴트 응답 MongoDB 저장
    """
    channel = f"{settings.CHAT_STREAM_PREFIX}{session_id}"

    # 1. 대화 히스토리 조회
    history_str = await get_context_within_limit(chat_repo, user_id, session_id)

    # 2. 3단계 LangGraph 파이프라인 실행
    final_answer = await run_pipeline(
        redis=redis,
        channel=channel,
        chat_history=history_str,
        question=message,
    )

    # 3. 종료 신호
    await _publish_event(redis, channel, "end")

    # 4. ChatHistory 저장 (MongoDB) — user message는 POST 시점에 이미 저장됨
    await chat_repo.save(session_id, user_id, "assistant", final_answer)
