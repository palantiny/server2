"""
SSE 채팅 API
POST /api/v1/chat/{session_id}/message: SSE 스트리밍 응답
process_message와 Queue 연동으로 thinking 과정 실시간 전달.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.database import get_redis
from app.services.chat_service import process_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    """SSE 채팅 요청 Body."""

    message: str = Field(..., min_length=1, description="사용자 질문 내용")
    user_id: str | None = Field(None, description="인증된 user_id (session_id에서 파싱 가능 시 생략)")


def _sse_format(data: dict) -> str:
    """SSE 표준 포맷: data: {JSON}\n\n"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _parse_user_id_from_session(session_id: str) -> str | None:
    """session_id가 {user_id}_{timestamp} 형식이면 user_id 추출."""
    parts = session_id.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return None


async def stream_chat_sse_real(
    chat_repo,
    redis,
    session_id: str,
    user_id: str,
    message: str,
):
    """Queue 기반 SSE: process_message의 send_fn → queue → yield."""
    queue: asyncio.Queue = asyncio.Queue()

    async def send_fn(payload: dict):
        await queue.put(payload)

    async def run_process():
        try:
            await process_message(
                chat_repo=chat_repo,
                redis=redis,
                session_id=session_id,
                user_id=user_id,
                message=message,
                send_fn=send_fn,
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_process())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse_format(item)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled: session_id=%s", session_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    except Exception as e:
        logger.exception("SSE stream error: %s", e)
        task.cancel()
        yield _sse_format({"type": "error", "content": str(e)})


@router.post("/{session_id}/message")
async def post_chat_message(session_id: str, body: ChatMessageRequest, request: Request):
    """
    POST /api/v1/chat/{session_id}/message
    Body: {"message": "...", "user_id": "..."} (user_id는 session_id에서 파싱 가능 시 생략)
    """
    user_id = body.user_id or _parse_user_id_from_session(session_id)
    if not user_id:
        raise HTTPException(status_code=422, detail="user_id required (in body or session_id)")

    chat_repo = getattr(request.app.state, "chat_repo", None)
    if not chat_repo:
        raise HTTPException(status_code=500, detail="chat_repo not initialized")

    redis = await get_redis()

    return StreamingResponse(
        stream_chat_sse_real(chat_repo, redis, session_id, user_id, body.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
