"""
SQL Worker - Redis Queue Consumer
DB 락 방지를 위해 Redis Queue를 사용. Chat Service가 LPUSH한 작업을 BRPOP으로 가져와
RDBMS에서 SQL 실행 후 결과를 result_key에 RPUSH.
"""
import asyncio
import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis에서 사용하는 Queue/키
SQL_TASK_QUEUE = settings.SQL_TASK_QUEUE
SQL_RESULT_PREFIX = settings.SQL_RESULT_PREFIX
SQL_RESULT_TTL = settings.SQL_RESULT_TTL


async def execute_sql_task(redis: Redis, task_payload: dict[str, Any]) -> None:
    """
    단일 SQL 작업 실행.
    task_payload: {task_id, sql, result_key}
    """
    task_id = task_payload.get("task_id")
    sql = task_payload.get("sql")
    result_key = task_payload.get("result_key")

    if not all([task_id, sql, result_key]):
        logger.warning("Invalid task payload: %s", task_payload)
        return

    # SELECT만 허용 (보안)
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        err = {"error": "Only SELECT queries are allowed"}
        await redis.rpush(result_key, json.dumps(err, ensure_ascii=False))
        await redis.expire(result_key, SQL_RESULT_TTL)
        return

    try:
        async with async_session_maker() as session:
            result = await session.execute(text(sql))
            rows = result.mappings().all()
            data = [dict(r) for r in rows]
            # datetime 등 JSON 직렬화를 위해 str 변환
            for row in data:
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        row[k] = v.isoformat()
                    elif hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
                        try:
                            row[k] = float(v)
                        except (TypeError, ValueError):
                            row[k] = str(v)

            await redis.rpush(result_key, json.dumps(data, ensure_ascii=False))
            await redis.expire(result_key, SQL_RESULT_TTL)
    except Exception as e:
        logger.exception("SQL execution failed: %s", e)
        err = {"error": str(e)}
        await redis.rpush(result_key, json.dumps(err, ensure_ascii=False))
        await redis.expire(result_key, SQL_RESULT_TTL)


async def run_sql_worker(redis: Redis) -> None:
    """
    SQL Worker 메인 루프.
    sql_task_queue에서 BRPOP으로 작업을 가져와 실행.
    """
    logger.info("SQL Worker started")
    while True:
        try:
            # BRPOP: 블로킹으로 대기 (타임아웃 5초)
            result = await redis.brpop(SQL_TASK_QUEUE, timeout=5)
            if result is None:
                continue

            _, payload_str = result
            task_payload = json.loads(payload_str)
            await execute_sql_task(redis, task_payload)
        except asyncio.CancelledError:
            logger.info("SQL Worker cancelled")
            break
        except Exception as e:
            logger.exception("SQL Worker error: %s", e)
            await asyncio.sleep(1)
