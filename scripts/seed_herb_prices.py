"""
한약재 가격표 CSV → PostgreSQL 시드 스크립트

CSV 파일 2개(국산/수입)를 파싱하여:
  1. herb_price_item 테이블에 약재 항목 삽입
  2. herb_price_history 테이블에 월별 가격 이력 삽입

실행: python -m scripts.seed_herb_prices (프로젝트 루트에서)
"""
import asyncio
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import async_session_maker, init_db
from app.models.herb_price import HerbPriceHistory, HerbPriceItem

# CSV 파일 경로
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_FILES = [
    (BASE_DIR / "(원외탕전실용)한약재가격표종합 - 국산.csv", "국산"),
    (BASE_DIR / "(원외탕전실용)한약재가격표종합 - 수입.csv", "수입"),
]

# 월별 컬럼 매핑 (col_index → year-month)
# Col 15-16: 25년 2월, Col 17-18: 25년 3월, ..., Col 35-36: 25년 12월, Col 37-38: 26년 2월
MONTH_COLUMNS = [
    (15, 16, "2025-02"),
    (17, 18, "2025-03"),
    (19, 20, "2025-04"),
    (21, 22, "2025-05"),
    (23, 24, "2025-06"),
    (25, 26, "2025-07"),
    (27, 28, "2025-08"),
    (29, 30, "2025-09"),
    (31, 32, "2025-10"),
    (33, 34, "2025-11"),
    (35, 36, "2025-12"),
    (37, 38, "2026-02"),
]


def parse_number(val: str) -> float | None:
    """숫자 문자열 파싱. 쉼표/공백 제거. 비숫자면 None."""
    if not val:
        return None
    cleaned = val.strip().replace(",", "").replace('"', "")
    if not cleaned:
        return None
    # "시세", "시세확인", "재고없음" 등 텍스트는 None
    if re.search(r"[가-힣a-zA-Z]", cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(val: str) -> int | None:
    """정수 파싱."""
    num = parse_number(val)
    if num is not None:
        return int(num)
    return None


def safe_get(row: list[str], idx: int) -> str:
    """안전한 인덱스 접근."""
    if idx < len(row):
        return row[idx].strip()
    return ""


def parse_csv(filepath: Path, source_type: str) -> tuple[list[dict], list[dict]]:
    """
    CSV 파일을 파싱하여 (items, histories) 반환.

    items: herb_price_item 레코드 리스트
    histories: herb_price_history 레코드 리스트
    """
    items = []
    histories = []

    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 데이터는 row 3부터 (row 0=제목, 1=서브헤더, 2=컬럼명)
    for row in rows[3:]:
        code = safe_get(row, 0).strip()
        herb_name = safe_get(row, 1).strip()

        # 빈 행 또는 코드/약재명 없는 행 스킵
        if not code or not herb_name:
            continue

        # 줄바꿈 문자 정리
        herb_name = herb_name.replace("\n", " ").replace("\r", "").strip()
        code = code.replace("\n", "").replace("\r", "").strip()

        item = {
            "code": code,
            "herb_name": herb_name,
            "origin": safe_get(row, 2) or None,
            "grade": safe_get(row, 3) or None,
            "source_type": source_type,
            "price_per_geun": parse_number(safe_get(row, 4)),
            "packaging_unit_g": parse_int(safe_get(row, 5)),
            "packaging_unit_price": parse_number(safe_get(row, 6)),
            "box_quantity": parse_int(safe_get(row, 7)),
            "subscription_price": parse_number(safe_get(row, 8)),
            "subscription_unit_g": parse_int(safe_get(row, 9)),
            "subscription_unit_price": parse_number(safe_get(row, 10)),
            "subscription_box_qty": parse_int(safe_get(row, 11)),
            "manufacturer": safe_get(row, 12) or None,
            "note": safe_get(row, 13) or None,
            "discount_rate": safe_get(row, 14) or None,
        }
        items.append(item)

        # 월별 가격 이력
        item_histories = []
        for reg_col, sub_col, year_month in MONTH_COLUMNS:
            reg_price = parse_number(safe_get(row, reg_col))
            sub_price = parse_number(safe_get(row, sub_col))
            if reg_price is not None or sub_price is not None:
                item_histories.append({
                    "year_month": year_month,
                    "regular_price": reg_price,
                    "subscription_price": sub_price,
                })
        histories.append(item_histories)

    return items, histories


async def seed():
    """CSV 데이터를 PostgreSQL에 삽입."""
    await init_db()

    async with async_session_maker() as session:
        # 기존 데이터 삭제 (idempotent)
        await session.execute(text("DELETE FROM herb_price_history"))
        await session.execute(text("DELETE FROM herb_price_item"))
        await session.commit()
        print("기존 herb_price 데이터 삭제 완료")

        total_items = 0
        total_history = 0

        for csv_path, source_type in CSV_FILES:
            if not csv_path.exists():
                print(f"파일 없음: {csv_path}")
                continue

            items, histories = parse_csv(csv_path, source_type)
            print(f"\n[{source_type}] {csv_path.name}: {len(items)}개 항목 파싱 완료")

            for i, item_data in enumerate(items):
                # HerbPriceItem 생성
                item = HerbPriceItem(**item_data)
                session.add(item)
                await session.flush()  # id 확정

                # 월별 이력 생성
                for hist_data in histories[i]:
                    history = HerbPriceHistory(
                        item_id=item.id,
                        **hist_data,
                    )
                    session.add(history)
                    total_history += 1

                total_items += 1

            await session.commit()
            print(f"[{source_type}] DB 삽입 완료: {len(items)}개 항목")

        print(f"\n전체 완료: {total_items}개 항목, {total_history}개 월별 이력 레코드")

        # 검증 쿼리
        result = await session.execute(text("SELECT COUNT(*) FROM herb_price_item"))
        item_count = result.scalar()
        result = await session.execute(text("SELECT COUNT(*) FROM herb_price_history"))
        hist_count = result.scalar()
        print(f"DB 검증: herb_price_item={item_count}, herb_price_history={hist_count}")

        # 샘플 출력
        result = await session.execute(text("""
            SELECT i.code, i.herb_name, i.source_type, i.price_per_geun, i.manufacturer,
                   COUNT(h.id) AS history_count
            FROM herb_price_item i
            LEFT JOIN herb_price_history h ON h.item_id = i.id
            GROUP BY i.id, i.code, i.herb_name, i.source_type, i.price_per_geun, i.manufacturer
            ORDER BY i.herb_name
            LIMIT 10
        """))
        print("\n[샘플 데이터]")
        print(f"{'코드':<12} {'약재명':<10} {'구분':<5} {'근당가격':>10} {'제약사':<10} {'이력수':>5}")
        print("-" * 60)
        for row in result:
            price = f"{row[3]:,.0f}" if row[3] else "N/A"
            print(f"{row[0]:<12} {row[1]:<10} {row[2]:<5} {price:>10} {row[4] or '-':<10} {row[5]:>5}")


if __name__ == "__main__":
    asyncio.run(seed())
