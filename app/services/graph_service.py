"""
한약재 지식 그래프 서비스 (Mock)
실제 Ontology/Knowledge Graph 대신 Python 딕셔너리로 탐색 로직 구현.
GRAPH 라우팅 시 한약재 효능, 관계, 원산지 등 조회.
"""
from typing import Any

# 한약재 Ontology Mock 데이터
# 실제 운영 시 Neo4j, RDF 등으로 대체 가능
HERB_ONTOLOGY: dict[str, dict[str, Any]] = {
    "감초": {
        "efficacy": "보익기, 화해제독, 완급조제",
        "related": ["대추", "생강", "인삼"],
        "origin": "중국, 몽골",
        "description": "맛이 달고 성질이 평하며, 기를 보하고 독을 풀어주며 약성의 완급을 조절합니다.",
    },
    "대추": {
        "efficacy": "보혈안신, 건비위",
        "related": ["감초", "인삼", "생강"],
        "origin": "한국, 중국",
        "description": "맛이 달고 성질이 따뜻하며, 혈을 보하고 신경을 안정시키며 비위를 튼튼하게 합니다.",
    },
    "생강": {
        "efficacy": "온중산한, 지해구담",
        "related": ["대추", "감초", "계피"],
        "origin": "한국, 중국, 인도",
        "description": "맛이 맵고 성질이 따뜻하며, 위를 따뜻하게 하고 한사를 제거합니다.",
    },
    "인삼": {
        "efficacy": "대보원기, 보비익폐, 생진지갈",
        "related": ["대추", "감초", "황기"],
        "origin": "한국, 중국",
        "description": "기운을 크게 보하고 비폐를 보하며 진액을 생기게 하고 갈증을 멈춥니다.",
    },
    "황기": {
        "efficacy": "보기승양, 고표생진",
        "related": ["인삼", "당귀"],
        "origin": "중국, 몽골",
        "description": "기를 보하고 양기를 올리며 표를 고하고 진액을 생기게 합니다.",
    },
    "당귀": {
        "efficacy": "보혈활혈, 윤조장통",
        "related": ["황기", "천궁", "백작"],
        "origin": "중국, 한국",
        "description": "혈을 보하고 혈행을 촉진하며 장부를 윤택하게 하고 통증을 완화합니다.",
    },
    "계피": {
        "efficacy": "보화양원, 산한지통",
        "related": ["생강", "부자"],
        "origin": "베트남, 스리랑카",
        "description": "양기를 보하고 원기를 돕으며 한사를 제거하고 통증을 멈춥니다.",
    },
}


async def search_herb_graph(query: str, extracted_entities: dict[str, Any] | None = None) -> str:
    """
    한약재 지식 그래프 Mock 탐색.
    query와 extracted_entities의 herb_name으로 관련 정보 반환.
    """
    herb_name = None
    if extracted_entities and extracted_entities.get("herb_name"):
        herb_name = extracted_entities["herb_name"]

    # herb_name이 없으면 query에서 한약재명 추출 시도
    if not herb_name:
        for name in HERB_ONTOLOGY:
            if name in query:
                herb_name = name
                break

    if herb_name and herb_name in HERB_ONTOLOGY:
        data = HERB_ONTOLOGY[herb_name]
        lines = [
            f"한약재: {herb_name}",
            f"효능: {data['efficacy']}",
            f"원산지: {data['origin']}",
            f"설명: {data['description']}",
            f"관련 한약재: {', '.join(data['related'])}",
        ]
        return "\n".join(lines)

    # 여러 한약재 검색 (query에 포함된 모든 한약재)
    results = []
    for name in HERB_ONTOLOGY:
        if name in query:
            data = HERB_ONTOLOGY[name]
            results.append(f"{name}: 효능={data['efficacy']}, 원산지={data['origin']}")

    if results:
        return "\n".join(results)

    # 매칭 없으면 전체 목록 요약
    return "등록된 한약재: " + ", ".join(HERB_ONTOLOGY.keys()) + ". 특정 한약재 이름을 말씀해 주시면 자세히 안내해 드리겠습니다."
