"""
WebSocket 채팅 API: WS /api/v1/chat/{session_id}
실시간 양방향 통신, Chat Service 연동.
"""
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_db
from app.core.database import get_redis
from app.services.chat_service import process_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.websocket("/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """
    WebSocket 채팅 엔드포인트.
    클라이언트는 JSON {"message": "..."} 형태로 메시지 전송.
    서버는 {"type": "status"|"token"|"end", "content": "..."} 형태로 응답.
    """
    await websocket.accept()

    # user_id: auth/verify의 session_id가 {user_id}_{timestamp} 형태이므로 파싱 가능
    # 또는 클라이언트가 메시지에 user_id 포함
    parts = session_id.rsplit("_", 1)
    user_id = parts[0] if len(parts) == 2 and parts[1].isdigit() else None

    redis = await get_redis()

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                msg = payload.get("message", "").strip()
                uid = payload.get("user_id") or user_id
                if not uid:
                    await websocket.send_json({"type": "error", "content": "user_id is required (in message or session_id)"})
                    continue
                if not msg:
                    await websocket.send_json({"type": "error", "content": "message is required"})
                    continue

                async def send_ws(p: dict):
                    await websocket.send_json(p)

                from app.core.database import async_session_maker

                async with async_session_maker() as db:
                    await process_message(
                        db=db,
                        redis=redis,
                        session_id=session_id,
                        user_id=uid,
                        message=msg,
                        send_fn=send_ws,
                    )
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "Invalid JSON"})
            except Exception as e:
                logger.exception("Chat processing error: %s", e)
                await websocket.send_json({"type": "error", "content": str(e)})
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", session_id)
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
