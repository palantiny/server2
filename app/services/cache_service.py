"""
Redis 스마트 캐싱 서비스
- Frequency-Based Caching: 2회 이상 참조된 약재만 캐시 적재
- Dynamic Caching: Cache Miss 시 DB 조회, 접근 횟수 충족 시 TTL(1h) 부여 적재
- Cache Invalidation: 원본 데이터 변경 시 해당 키 + 접근 카운터 삭제
"""
import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text

from app.core.database import async_session_maker, get_redis

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────
CACHE_PREFIX = "herb:cache:"
ACCESS_COUNT_PREFIX = "herb:access:"
DYNAMIC_TTL = 3600  # 동적 캐시 TTL: 1시간
ACCESS_COUNT_TTL = 86400  # 접근 카운터 TTL: 24시간
CACHE_THRESHOLD = 2  # 이 횟수 이상 접근 시 캐시 적재


# ── 내부 유틸 ─────────────────────────────────────────
def _cache_key(herb_name: str) -> str:
    """약재명 기반 캐시 키 생성."""
    return f"{CACHE_PREFIX}{herb_name}"


def _access_key(herb_name: str) -> str:
    """약재명 기반 접근 카운터 키 생성."""
    return f"{ACCESS_COUNT_PREFIX}{herb_name}"


def _serialize(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _deserialize(raw: str) -> dict | list:
    return json.loads(raw)


# ── 1) Cache Get (Frequency-Based Dynamic Caching) ───
async def get_herb_cache(herb_name: str) -> dict | None:
    """
    캐시 조회.
    - Hit → 파싱 후 반환.
    - Miss → DB 조회 + 접근 횟수 증가. 2회 이상이면 캐시 적재(TTL 1h).
    - DB에도 없으면 None.
    """
    redis = await get_redis()
    key = _cache_key(herb_name)

    # Cache Hit
    raw = await redis.get(key)
    if raw is not None:
        logger.info("Cache HIT: %s", herb_name)
        return _deserialize(raw)

    # Cache Miss → DB 조회
    logger.info("Cache MISS: %s → DB fallback", herb_name)
    data = await _fetch_herb_from_db(herb_name)
    if data is None:
        return None

    # 접근 횟수 증가 (24시간 TTL 카운터)
    access_key = _access_key(herb_name)
    count = await redis.incr(access_key)
    if count == 1:
        await redis.expire(access_key, ACCESS_COUNT_TTL)

    # 2회 이상 접근 시에만 캐시 적재
    if count >= CACHE_THRESHOLD:
        await redis.set(key, _serialize(data), ex=DYNAMIC_TTL)
        logger.info("Cache SET (access=%d): %s (TTL=%ds)", count, herb_name, DYNAMIC_TTL)
    else:
        logger.info("Cache SKIP (access=%d/%d): %s", count, CACHE_THRESHOLD, herb_name)

    return data


async def set_herb_cache(herb_name: str, data: dict, ttl: int = DYNAMIC_TTL) -> None:
    """명시적 캐시 설정. 접근 카운터와 무관하게 강제 적재."""
    redis = await get_redis()
    key = _cache_key(herb_name)
    await redis.set(key, _serialize(data), ex=ttl)


async def get_herbs_bulk(herb_names: list[str]) -> dict[str, dict | None]:
    """여러 약재를 한 번에 조회. MGET으로 네트워크 왕복 최소화."""
    redis = await get_redis()
    keys = [_cache_key(name) for name in herb_names]
    raw_values = await redis.mget(keys)

    result: dict[str, dict | None] = {}
    miss_names: list[str] = []

    for name, raw in zip(herb_names, raw_values):
        if raw is not None:
            result[name] = _deserialize(raw)
        else:
            result[name] = None
            miss_names.append(name)

    # Cache Miss 건은 get_herb_cache를 통해 접근 카운터 반영
    for name in miss_names:
        data = await get_herb_cache(name)
        result[name] = data

    return result


# ── 2) Cache Invalidation ────────────────────────────
async def invalidate_herb_cache(herb_name: str) -> bool:
    """
    원본 데이터 변경 시 해당 약재의 캐시 + 접근 카운터를 삭제.
    다음 조회 시 Cache Miss → 접근 카운터 1부터 다시 시작.
    """
    redis = await get_redis()
    key = _cache_key(herb_name)
    access_key = _access_key(herb_name)
    deleted = await redis.delete(key, access_key)
    if deleted:
        logger.info("Cache INVALIDATED: %s", herb_name)
    return bool(deleted)


async def invalidate_herbs_bulk(herb_names: list[str]) -> int:
    """여러 약재 캐시 + 접근 카운터 일괄 무효화."""
    if not herb_names:
        return 0
    redis = await get_redis()
    keys = []
    for name in herb_names:
        keys.append(_cache_key(name))
        keys.append(_access_key(name))
    deleted = await redis.delete(*keys)
    logger.info("Cache INVALIDATED (bulk): %d keys", deleted)
    return deleted


async def invalidate_all_herb_cache() -> int:
    """herb:cache:* + herb:access:* 전체 삭제."""
    redis = await get_redis()
    total_deleted = 0
    for pattern in (f"{CACHE_PREFIX}*", f"{ACCESS_COUNT_PREFIX}*"):
        cursor = "0"
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor, match=pattern, count=200,
            )
            if keys:
                total_deleted += await redis.delete(*keys)
            if cursor == 0:
                break
    logger.info("Cache INVALIDATED (all): %d keys", total_deleted)
    return total_deleted


# ── 내부: DB Fallback 조회 ───────────────────────────
async def _fetch_herb_from_db(herb_name: str) -> dict | None:
    """
    DB에서 약재 관련 전체 정보를 조회하여 캐시 value 형태의 dict로 반환.
    herb_master(기본 정보) + herb_price_item(가격) + inventory(재고) + herb_price_history(가격 이력)
    """
    async with async_session_maker() as session:
        # herb_master 기본 정보
        master_result = await session.execute(text("""
            SELECT herb_id, name, origin, efficacy
            FROM herb_master
            WHERE name = :name
        """), {"name": herb_name})
        master_rows = master_result.fetchall()

        # herb_price_item 가격 정보
        price_result = await session.execute(text("""
            SELECT
                code, herb_name, origin, grade, source_type,
                price_per_geun, packaging_unit_g, packaging_unit_price, box_quantity,
                subscription_price, subscription_unit_g, subscription_unit_price,
                subscription_box_qty, manufacturer, note, discount_rate
            FROM herb_price_item
            WHERE herb_name = :name
        """), {"name": herb_name})
        price_rows = price_result.fetchall()

        # inventory + herb_master 재고 정보
        inv_result = await session.execute(text("""
            SELECT
                hm.name, hm.origin, hm.efficacy,
                inv.partner_id, inv.stock_quantity, inv.price
            FROM inventory inv
            JOIN herb_master hm ON hm.herb_id = inv.herb_id
            WHERE hm.name = :name
        """), {"name": herb_name})
        inv_rows = inv_result.fetchall()

        # herb_price_history 가격 이력
        history_result = await session.execute(text("""
            SELECT
                h.year_month, h.regular_price, h.subscription_price,
                i.herb_name, i.code
            FROM herb_price_history h
            JOIN herb_price_item i ON i.id = h.item_id
            WHERE i.herb_name = :name
            ORDER BY h.year_month DESC
        """), {"name": herb_name})
        history_rows = history_result.fetchall()

    if not master_rows and not price_rows and not inv_rows:
        return None

    data: dict[str, Any] = {
        "herb_name": herb_name,
        "master": [],
        "price_items": [],
        "inventory": [],
        "price_history": [],
    }

    for row in master_rows:
        data["master"].append({
            "herb_id": str(row[0]),
            "name": row[1],
            "origin": row[2],
            "efficacy": row[3],
        })

    for row in price_rows:
        data["price_items"].append({
            "code": row[0],
            "origin": row[2],
            "grade": row[3],
            "source_type": row[4],
            "price_per_geun": float(row[5]) if row[5] is not None else None,
            "packaging_unit_g": row[6],
            "packaging_unit_price": float(row[7]) if row[7] is not None else None,
            "box_quantity": row[8],
            "subscription_price": float(row[9]) if row[9] is not None else None,
            "subscription_unit_g": row[10],
            "subscription_unit_price": float(row[11]) if row[11] is not None else None,
            "subscription_box_qty": row[12],
            "manufacturer": row[13],
            "note": row[14],
            "discount_rate": row[15],
        })

    for row in inv_rows:
        data["inventory"].append({
            "origin": row[1],
            "efficacy": row[2],
            "partner_id": row[3],
            "stock_quantity": row[4],
            "price": float(row[5]) if row[5] is not None else None,
        })

    for row in history_rows:
        data["price_history"].append({
            "year_month": row[0],
            "regular_price": float(row[1]) if row[1] is not None else None,
            "subscription_price": float(row[2]) if row[2] is not None else None,
            "code": row[4],
        })

    return data
