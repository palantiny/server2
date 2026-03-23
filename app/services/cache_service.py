"""
Redis 스마트 캐싱 서비스
- Cache Warming: 서버 기동 시 RDBMS → Redis 사전 적재
- Dynamic Caching: Cache Miss 시 DB 조회 후 TTL(1h) 부여 적재
- Cache Invalidation: 원본 데이터 변경 시 해당 키 삭제
"""
import json
import logging
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, text

from app.core.database import async_session_maker, get_redis

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────
CACHE_PREFIX = "herb:cache:"
DYNAMIC_TTL = 3600  # 동적 캐시 TTL: 1시간


# ── 내부 유틸 ─────────────────────────────────────────
def _cache_key(herb_name: str) -> str:
    """약재명 기반 캐시 키 생성."""
    return f"{CACHE_PREFIX}{herb_name}"


def _serialize(data: dict | list) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _deserialize(raw: str) -> dict | list:
    return json.loads(raw)


# ── 1) Cache Warming ─────────────────────────────────
async def warm_cache() -> int:
    """
    서버 기동 시 호출. herb_price_item + inventory 데이터를
    약재명 기준으로 그룹핑하여 Redis에 사전 적재.
    워밍 데이터는 TTL 없이 영구 보관 (LRU에 의해서만 퇴거).

    Returns:
        적재된 캐시 키 수.
    """
    redis = await get_redis()
    count = 0

    async with async_session_maker() as session:
        # ── herb_price_item 데이터 로드 ──
        result = await session.execute(text("""
            SELECT
                i.herb_name,
                i.code,
                i.origin,
                i.grade,
                i.source_type,
                i.price_per_geun,
                i.packaging_unit_g,
                i.packaging_unit_price,
                i.box_quantity,
                i.subscription_price,
                i.subscription_unit_g,
                i.subscription_unit_price,
                i.subscription_box_qty,
                i.manufacturer,
                i.note,
                i.discount_rate
            FROM herb_price_item i
            ORDER BY i.herb_name
        """))
        price_rows = result.fetchall()

        # ── inventory + herb_master 재고 데이터 로드 ──
        inv_result = await session.execute(text("""
            SELECT
                hm.name AS herb_name,
                hm.origin,
                hm.efficacy,
                inv.partner_id,
                inv.stock_quantity,
                inv.price
            FROM inventory inv
            JOIN herb_master hm ON hm.herb_id = inv.herb_id
            ORDER BY hm.name
        """))
        inv_rows = inv_result.fetchall()

    # ── 약재명 기준 그룹핑 ──
    herb_data: dict[str, dict[str, Any]] = {}

    # 가격표 데이터 그룹핑
    for row in price_rows:
        name = row[0]
        if name not in herb_data:
            herb_data[name] = {"herb_name": name, "price_items": [], "inventory": []}

        herb_data[name]["price_items"].append({
            "code": row[1],
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

    # 재고 데이터 그룹핑
    for row in inv_rows:
        name = row[0]
        if name not in herb_data:
            herb_data[name] = {"herb_name": name, "price_items": [], "inventory": []}

        herb_data[name]["inventory"].append({
            "origin": row[1],
            "efficacy": row[2],
            "partner_id": row[3],
            "stock_quantity": row[4],
            "price": float(row[5]) if row[5] is not None else None,
        })

    # ── Redis 적재 (pipeline 사용으로 네트워크 왕복 최소화) ──
    pipe = redis.pipeline(transaction=False)
    for herb_name, data in herb_data.items():
        key = _cache_key(herb_name)
        pipe.set(key, _serialize(data))
        # 워밍 데이터는 TTL 없음 → LRU에 의해서만 퇴거
    await pipe.execute()
    count = len(herb_data)

    logger.info("Cache warming 완료: %d개 약재 캐시 적재", count)
    return count


# ── 2) Cache Get / Set (Dynamic Caching) ─────────────
async def get_herb_cache(herb_name: str) -> dict | None:
    """
    캐시 조회. Hit 시 파싱 후 반환, Miss 시 DB 조회 → 캐시 적재(TTL 1h) 후 반환.
    DB에도 없으면 None.
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

    # 동적 캐시 적재 (TTL 1시간)
    await redis.set(key, _serialize(data), ex=DYNAMIC_TTL)
    logger.info("Dynamic cache SET: %s (TTL=%ds)", herb_name, DYNAMIC_TTL)
    return data


async def set_herb_cache(herb_name: str, data: dict, ttl: int = DYNAMIC_TTL) -> None:
    """명시적 캐시 설정. 동적 캐시이므로 TTL 부여."""
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

    # Cache Miss 건은 개별 DB 조회 후 적재
    for name in miss_names:
        data = await _fetch_herb_from_db(name)
        if data is not None:
            await set_herb_cache(name, data)
        result[name] = data

    return result


# ── 3) Cache Invalidation ────────────────────────────
async def invalidate_herb_cache(herb_name: str) -> bool:
    """
    원본 데이터(재고/가격) 변경 시 해당 약재의 캐시를 삭제.
    다음 조회 시 Cache Miss → DB 최신값 재적재.

    Returns:
        True if key existed and was deleted, False otherwise.
    """
    redis = await get_redis()
    key = _cache_key(herb_name)
    deleted = await redis.delete(key)
    if deleted:
        logger.info("Cache INVALIDATED: %s", herb_name)
    return bool(deleted)


async def invalidate_herbs_bulk(herb_names: list[str]) -> int:
    """여러 약재 캐시 일괄 무효화."""
    if not herb_names:
        return 0
    redis = await get_redis()
    keys = [_cache_key(name) for name in herb_names]
    deleted = await redis.delete(*keys)
    logger.info("Cache INVALIDATED (bulk): %d/%d keys", deleted, len(herb_names))
    return deleted


async def invalidate_all_herb_cache() -> int:
    """herb:cache:* 패턴의 모든 캐시 키 삭제. 전체 재적재 전 사용."""
    redis = await get_redis()
    cursor = "0"
    total_deleted = 0
    while cursor:
        cursor, keys = await redis.scan(
            cursor=cursor, match=f"{CACHE_PREFIX}*", count=200,
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
    DB에서 약재 정보를 조회하여 캐시 value 형태의 dict로 반환.
    herb_price_item + inventory 양쪽 모두 조회.
    """
    async with async_session_maker() as session:
        # herb_price_item 조회 (LIKE 검색으로 부분 일치도 허용)
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

        # inventory + herb_master 조회
        inv_result = await session.execute(text("""
            SELECT
                hm.name, hm.origin, hm.efficacy,
                inv.partner_id, inv.stock_quantity, inv.price
            FROM inventory inv
            JOIN herb_master hm ON hm.herb_id = inv.herb_id
            WHERE hm.name = :name
        """), {"name": herb_name})
        inv_rows = inv_result.fetchall()

    if not price_rows and not inv_rows:
        return None

    data: dict[str, Any] = {
        "herb_name": herb_name,
        "price_items": [],
        "inventory": [],
    }

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

    return data
