"""
한약재 지식 그래프 서비스 (Neo4j)
"""
import logging
from typing import Any

from neo4j import AsyncGraphDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Neo4j 드라이버 (싱글톤) ──────────────────────────
_driver = None


async def get_neo4j_driver():
    """Neo4j 비동기 드라이버 반환 (지연 초기화)."""
    global _driver
    if _driver is None and settings.NEO4J_URI:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j():
    """Neo4j 드라이버 종료."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


# ── Neo4j 쿼리 ───────────────────────────────────────
async def _query_neo4j(herb_name: str) -> str | None:
    """Neo4j에서 약재 정보 + 관계 조회."""
    driver = await get_neo4j_driver()
    if not driver:
        return None

    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(
                """
                MATCH (h:Herb {name: $name})
                OPTIONAL MATCH (h)-[:RELATED_TO]-(related:Herb)
                OPTIONAL MATCH (h)-[:ORIGINATES_FROM]->(o:Origin)
                RETURN h.name AS name,
                       h.efficacy AS efficacy,
                       h.description AS description,
                       h.nature AS nature,
                       h.flavor AS flavor,
                       COLLECT(DISTINCT related.name) AS related_herbs,
                       COLLECT(DISTINCT o.name) AS origins
                """,
                name=herb_name,
            )
            record = await result.single()

            if not record or not record["name"]:
                return None

            lines = [f"한약재: {record['name']}"]
            if record["efficacy"]:
                lines.append(f"효능: {record['efficacy']}")
            if record["nature"]:
                lines.append(f"성질: {record['nature']}")
            if record["flavor"]:
                lines.append(f"맛: {record['flavor']}")
            origins = [o for o in record["origins"] if o]
            if origins:
                lines.append(f"원산지: {', '.join(origins)}")
            if record["description"]:
                lines.append(f"설명: {record['description']}")
            related = [r for r in record["related_herbs"] if r]
            if related:
                lines.append(f"관련 한약재: {', '.join(related)}")
            return "\n".join(lines)
    except Exception as e:
        logger.exception("Neo4j 쿼리 실패: %s", e)
        return None


async def _search_neo4j_all(query: str) -> str | None:
    """Neo4j에서 query에 포함된 약재 또는 전체 목록 조회."""
    driver = await get_neo4j_driver()
    if not driver:
        return None

    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as session:
            # 전체 약재 중 이름에 query 키워드가 포함된 것 검색
            result = await session.run(
                """
                MATCH (h:Herb)
                WHERE h.name CONTAINS $keyword
                OPTIONAL MATCH (h)-[:ORIGINATES_FROM]->(o:Origin)
                RETURN h.name AS name, h.efficacy AS efficacy,
                       COLLECT(DISTINCT o.name) AS origins
                LIMIT 10
                """,
                keyword=query,
            )
            records = [r async for r in result]

            if not records:
                # 전체 약재 목록 반환
                result = await session.run(
                    "MATCH (h:Herb) RETURN h.name AS name ORDER BY h.name LIMIT 50"
                )
                names = [r["name"] async for r in result]
                if names:
                    return f"등록된 한약재: {', '.join(names)}. 특정 한약재 이름을 말씀해 주시면 자세히 안내해 드리겠습니다."
                return None

            lines = []
            for r in records:
                origins = [o for o in r["origins"] if o]
                origin_str = f", 원산지={', '.join(origins)}" if origins else ""
                lines.append(f"{r['name']}: 효능={r['efficacy']}{origin_str}")
            return "\n".join(lines)
    except Exception as e:
        logger.exception("Neo4j 전체 검색 실패: %s", e)
        return None


# ── 외부 인터페이스 ──────────────────────────────────
async def search_herb_graph(query: str, extracted_entities: dict[str, Any] | None = None) -> str:
    """
    한약재 지식 그래프 탐색 (Neo4j).
    """
    herb_name = None
    if extracted_entities and extracted_entities.get("herb_name"):
        herb_name = extracted_entities["herb_name"]

    # Neo4j 조회
    if herb_name:
        neo4j_result = await _query_neo4j(herb_name)
        if neo4j_result:
            return neo4j_result
        return f"'{herb_name}'에 대한 지식 그래프 정보가 없습니다."

    neo4j_result = await _search_neo4j_all(query)
    if neo4j_result:
        return neo4j_result

    return "지식 그래프에서 관련 정보를 찾지 못했습니다. 특정 한약재 이름을 말씀해 주시면 자세히 안내해 드리겠습니다."
