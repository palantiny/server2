"""
Palantiny DB 및 Redis 연결 모듈
비동기 SQLAlchemy 엔진, 세션 팩토리, Redis 클라이언트 설정.
"""
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Base

settings = get_settings()

# SQLAlchemy 비동기 엔진 (PostgreSQL)
# asyncpg 드라이버 사용으로 고성능 비동기 DB 접근
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# 세션 팩토리: 각 요청마다 새 AsyncSession 생성
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# Redis 클라이언트 (비동기)
# Queue(LPUSH/BRPOP), Pub/Sub, 캐시 등에 사용
redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Redis 클라이언트 반환. 앱 lifespan에서 초기화."""
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def init_db() -> None:
    """테이블 생성 (개발용). 프로덕션에서는 Alembic 마이그레이션 사용 권장."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """엔진 종료."""
    await engine.dispose()


async def close_redis() -> None:
    """Redis 연결 종료."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
