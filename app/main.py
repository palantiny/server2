"""
Palantiny Chatbot Server - FastAPI 진입점
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, chat
from app.core.database import close_db, close_redis, get_redis, init_db
from app.services.sql_worker import run_sql_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB/Redis 초기화, SQL Worker 백그라운드 시작. 종료 시 정리."""
    # Startup
    await init_db()
    redis = await get_redis()
    worker_task = asyncio.create_task(run_sql_worker(redis))
    logger.info("Palantiny server started")
    yield
    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await close_redis()
    await close_db()
    logger.info("Palantiny server stopped")


app = FastAPI(
    title="Palantiny Chatbot API",
    description="한약재 유통 B2B2C 챗봇 서버",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 라우터
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")


@app.get("/health")
async def health():
    """헬스 체크."""
    return {"status": "ok"}
