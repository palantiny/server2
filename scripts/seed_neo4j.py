"""
Neo4j 한약재 지식 그래프 시드 스크립트
Herb 노드, Origin 노드, 관계(RELATED_TO, ORIGINATES_FROM) 생성.

실행: python3 scripts/seed_neo4j.py
"""
import asyncio

from neo4j import AsyncGraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "palantiny_secret"
NEO4J_DATABASE = "neo4j"

# ── 한약재 지식 데이터 ───────────────────────────────
HERBS = [
    {
        "name": "감초",
        "efficacy": "보익기, 화해제독, 완급조제",
        "description": "맛이 달고 성질이 평하며, 기를 보하고 독을 풀어주며 약성의 완급을 조절합니다.",
        "origins": ["중국", "몽골"],
        "nature": "평(平)",
        "flavor": "감(甘)",
    },
    {
        "name": "대추",
        "efficacy": "보혈안신, 건비위",
        "description": "맛이 달고 성질이 따뜻하며, 혈을 보하고 신경을 안정시키며 비위를 튼튼하게 합니다.",
        "origins": ["한국", "중국"],
        "nature": "온(溫)",
        "flavor": "감(甘)",
    },
    {
        "name": "생강",
        "efficacy": "온중산한, 지해구담",
        "description": "맛이 맵고 성질이 따뜻하며, 위를 따뜻하게 하고 한사를 제거합니다.",
        "origins": ["한국", "중국", "인도"],
        "nature": "온(溫)",
        "flavor": "신(辛)",
    },
    {
        "name": "인삼",
        "efficacy": "대보원기, 보비익폐, 생진지갈",
        "description": "기운을 크게 보하고 비폐를 보하며 진액을 생기게 하고 갈증을 멈춥니다.",
        "origins": ["한국", "중국"],
        "nature": "온(溫)",
        "flavor": "감(甘), 미고(微苦)",
    },
    {
        "name": "황기",
        "efficacy": "보기승양, 고표생진, 이수소종, 탁창생기",
        "description": "기를 보하고 양기를 올리며 표를 고하고 진액을 생기게 합니다. 부종을 줄이고 창상 회복을 돕습니다.",
        "origins": ["중국", "몽골"],
        "nature": "온(溫)",
        "flavor": "감(甘)",
    },
    {
        "name": "당귀",
        "efficacy": "보혈활혈, 윤조장통, 조경지통",
        "description": "혈을 보하고 혈행을 촉진하며 장부를 윤택하게 하고 통증을 완화합니다.",
        "origins": ["중국", "한국"],
        "nature": "온(溫)",
        "flavor": "감(甘), 신(辛)",
    },
    {
        "name": "계피",
        "efficacy": "보화양원, 산한지통, 온경통맥",
        "description": "양기를 보하고 원기를 돕으며 한사를 제거하고 통증을 멈춥니다. 경맥을 따뜻하게 하여 혈행을 돕습니다.",
        "origins": ["베트남", "스리랑카", "중국"],
        "nature": "대열(大熱)",
        "flavor": "신(辛), 감(甘)",
    },
    {
        "name": "천궁",
        "efficacy": "활혈행기, 거풍지통",
        "description": "혈을 활발하게 하고 기를 운행시키며 풍사를 제거하고 통증을 멈춥니다.",
        "origins": ["한국", "중국"],
        "nature": "온(溫)",
        "flavor": "신(辛)",
    },
    {
        "name": "백작약",
        "efficacy": "양혈렴음, 유간지통, 평억간양",
        "description": "혈을 기르고 음을 거두며 간을 부드럽게 하고 통증을 멈춥니다.",
        "origins": ["중국", "한국"],
        "nature": "미한(微寒)",
        "flavor": "고(苦), 산(酸)",
    },
    {
        "name": "백출",
        "efficacy": "건비익기, 조습이수, 지한안태",
        "description": "비장을 튼튼히 하고 기를 보하며 습기를 말리고 소변을 잘 나오게 합니다.",
        "origins": ["중국", "한국"],
        "nature": "온(溫)",
        "flavor": "감(甘), 고(苦)",
    },
    {
        "name": "복령",
        "efficacy": "이수삼습, 건비녕심",
        "description": "수분을 잘 순환시키고 습기를 제거하며 비장을 튼튼히 하고 마음을 안정시킵니다.",
        "origins": ["중국", "한국"],
        "nature": "평(平)",
        "flavor": "감(甘), 담(淡)",
    },
    {
        "name": "숙지황",
        "efficacy": "보혈자음, 익정전수",
        "description": "혈을 보하고 음기를 자양하며 정기를 보충하고 골수를 채워줍니다.",
        "origins": ["중국", "한국"],
        "nature": "미온(微溫)",
        "flavor": "감(甘)",
    },
    {
        "name": "반하",
        "efficacy": "조습화담, 강역지구, 소비산결",
        "description": "습기를 말리고 담을 삭이며 역기를 내리고 구토를 멈추게 합니다.",
        "origins": ["중국", "한국"],
        "nature": "온(溫)",
        "flavor": "신(辛)",
    },
    {
        "name": "진피",
        "efficacy": "이기건비, 조습화담",
        "description": "기의 순행을 돕고 비위를 튼튼히 하며 습기를 말리고 담을 삭입니다.",
        "origins": ["중국", "한국"],
        "nature": "온(溫)",
        "flavor": "신(辛), 고(苦)",
    },
    {
        "name": "부자",
        "efficacy": "회양구역, 보화조양, 산한지통",
        "description": "양기를 회복시키고 명문의 화를 보하며 한사를 흩어 통증을 멈춥니다.",
        "origins": ["중국"],
        "nature": "대열(大熱)",
        "flavor": "신(辛), 감(甘)",
    },
    {
        "name": "지황",
        "efficacy": "청열양혈, 양음생진",
        "description": "열을 내리고 혈을 시원하게 하며 음기를 기르고 진액을 생성합니다.",
        "origins": ["중국", "한국"],
        "nature": "한(寒)",
        "flavor": "감(甘), 고(苦)",
    },
    {
        "name": "오미자",
        "efficacy": "렴폐자신, 생진렴한, 삽정지사",
        "description": "폐를 거두어 기침을 멈추고 신장을 자양하며 진액을 보충합니다.",
        "origins": ["한국", "중국"],
        "nature": "온(溫)",
        "flavor": "산(酸)",
    },
    {
        "name": "산수유",
        "efficacy": "보익간신, 수렴고삽",
        "description": "간과 신장을 보하고 정기를 거두어 유정, 야뇨 등을 치료합니다.",
        "origins": ["한국", "중국"],
        "nature": "미온(微溫)",
        "flavor": "산(酸), 삽(澁)",
    },
    {
        "name": "맥문동",
        "efficacy": "양음윤폐, 익위생진, 청심제번",
        "description": "음기를 기르고 폐를 윤택하게 하며 위를 보하고 진액을 생성합니다.",
        "origins": ["한국", "중국"],
        "nature": "미한(微寒)",
        "flavor": "감(甘), 미고(微苦)",
    },
    {
        "name": "택사",
        "efficacy": "이수삼습, 설열",
        "description": "수분을 소변으로 배출시키고 습기를 없애며 열을 내립니다.",
        "origins": ["중국", "한국"],
        "nature": "한(寒)",
        "flavor": "감(甘), 담(淡)",
    },
]

# ── 약재 간 관계 (RELATED_TO: 궁합/배합 관계) ────────
RELATIONSHIPS = [
    # 사군자탕 (四君子湯) 구성
    ("인삼", "백출"), ("인삼", "복령"), ("인삼", "감초"),
    ("백출", "복령"), ("백출", "감초"), ("복령", "감초"),
    # 사물탕 (四物湯) 구성
    ("숙지황", "당귀"), ("숙지황", "백작약"), ("숙지황", "천궁"),
    ("당귀", "백작약"), ("당귀", "천궁"), ("백작약", "천궁"),
    # 보중익기탕 핵심
    ("황기", "인삼"), ("황기", "당귀"), ("황기", "백출"),
    # 기타 대표적 궁합
    ("감초", "대추"), ("감초", "생강"), ("감초", "인삼"),
    ("대추", "생강"), ("대추", "인삼"),
    ("생강", "계피"), ("생강", "반하"),
    ("계피", "부자"),
    ("반하", "진피"),
    ("오미자", "맥문동"), ("오미자", "인삼"),  # 생맥산
    ("산수유", "숙지황"), ("산수유", "택사"),  # 육미지황환
    ("숙지황", "택사"), ("숙지황", "복령"),    # 육미지황환
]


async def seed():
    driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    async with driver.session(database=NEO4J_DATABASE) as session:
        # 기존 데이터 삭제
        await session.run("MATCH (n) DETACH DELETE n")
        print("기존 데이터 삭제 완료")

        # 인덱스 생성
        await session.run("CREATE INDEX herb_name IF NOT EXISTS FOR (h:Herb) ON (h.name)")
        await session.run("CREATE INDEX origin_name IF NOT EXISTS FOR (o:Origin) ON (o.name)")
        print("인덱스 생성 완료")

        # Origin 노드 생성 (중복 없이)
        all_origins = set()
        for herb in HERBS:
            all_origins.update(herb["origins"])

        for origin in all_origins:
            await session.run(
                "MERGE (o:Origin {name: $name})",
                name=origin,
            )
        print(f"Origin 노드 {len(all_origins)}개 생성")

        # Herb 노드 생성 + ORIGINATES_FROM 관계
        for herb in HERBS:
            await session.run(
                """
                MERGE (h:Herb {name: $name})
                SET h.efficacy = $efficacy,
                    h.description = $description,
                    h.nature = $nature,
                    h.flavor = $flavor
                """,
                name=herb["name"],
                efficacy=herb["efficacy"],
                description=herb["description"],
                nature=herb["nature"],
                flavor=herb["flavor"],
            )
            for origin in herb["origins"]:
                await session.run(
                    """
                    MATCH (h:Herb {name: $herb_name})
                    MATCH (o:Origin {name: $origin_name})
                    MERGE (h)-[:ORIGINATES_FROM]->(o)
                    """,
                    herb_name=herb["name"],
                    origin_name=origin,
                )
        print(f"Herb 노드 {len(HERBS)}개 생성 + ORIGINATES_FROM 관계 연결")

        # RELATED_TO 관계 생성 (양방향)
        for herb1, herb2 in RELATIONSHIPS:
            await session.run(
                """
                MATCH (a:Herb {name: $name1})
                MATCH (b:Herb {name: $name2})
                MERGE (a)-[:RELATED_TO]->(b)
                MERGE (b)-[:RELATED_TO]->(a)
                """,
                name1=herb1,
                name2=herb2,
            )
        print(f"RELATED_TO 관계 {len(RELATIONSHIPS)}개 생성")

        # 검증
        result = await session.run("MATCH (h:Herb) RETURN COUNT(h) AS cnt")
        record = await result.single()
        print(f"\n검증: Herb 노드 = {record['cnt']}개")

        result = await session.run("MATCH (o:Origin) RETURN COUNT(o) AS cnt")
        record = await result.single()
        print(f"검증: Origin 노드 = {record['cnt']}개")

        result = await session.run("MATCH ()-[r:RELATED_TO]->() RETURN COUNT(r) AS cnt")
        record = await result.single()
        print(f"검증: RELATED_TO 관계 = {record['cnt']}개")

        result = await session.run("MATCH ()-[r:ORIGINATES_FROM]->() RETURN COUNT(r) AS cnt")
        record = await result.single()
        print(f"검증: ORIGINATES_FROM 관계 = {record['cnt']}개")

        # 샘플 출력
        result = await session.run("""
            MATCH (h:Herb)
            OPTIONAL MATCH (h)-[:RELATED_TO]-(r:Herb)
            OPTIONAL MATCH (h)-[:ORIGINATES_FROM]->(o:Origin)
            RETURN h.name AS name, h.efficacy AS efficacy,
                   COLLECT(DISTINCT r.name) AS related,
                   COLLECT(DISTINCT o.name) AS origins
            ORDER BY h.name
            LIMIT 5
        """)
        print("\n[샘플 데이터]")
        async for r in result:
            print(f"  {r['name']}: 효능={r['efficacy']}, 관련={r['related']}, 원산지={r['origins']}")

    await driver.close()
    print("\nNeo4j 시드 완료!")


if __name__ == "__main__":
    asyncio.run(seed())
