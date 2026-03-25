"""
CSV → SQL INSERT 문 생성 스크립트 (외부 의존성 없음)
생성된 SQL을 psql로 직접 실행하여 데이터 삽입.
"""
import csv
import re
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_FILES = [
    (BASE_DIR / "(원외탕전실용)한약재가격표종합 - 국산.csv", "국산"),
    (BASE_DIR / "(원외탕전실용)한약재가격표종합 - 수입.csv", "수입"),
]
OUTPUT = BASE_DIR / "scripts" / "herb_price_seed.sql"

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


def parse_number(val: str):
    if not val:
        return None
    cleaned = val.strip().replace(",", "").replace('"', "")
    if not cleaned:
        return None
    if re.search(r"[가-힣a-zA-Z#]", cleaned):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(val: str):
    num = parse_number(val)
    if num is not None:
        return int(num)
    return None


def safe_get(row, idx):
    if idx < len(row):
        return row[idx].strip()
    return ""


def sql_str(val):
    """SQL 문자열 이스케이프."""
    if val is None:
        return "NULL"
    val = str(val).replace("'", "''").replace("\n", " ").replace("\r", "")
    return f"'{val}'"


def sql_num(val):
    if val is None:
        return "NULL"
    return str(val)


def main():
    lines = [
        "-- 한약재 가격표 시드 데이터",
        "-- Auto-generated from CSV files",
        "BEGIN;",
        "DELETE FROM herb_price_history;",
        "DELETE FROM herb_price_item;",
        "",
    ]

    total_items = 0
    total_hist = 0

    for csv_path, source_type in CSV_FILES:
        if not csv_path.exists():
            print(f"파일 없음: {csv_path}")
            continue

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        lines.append(f"-- [{source_type}] {csv_path.name}")

        for row in rows[3:]:
            code = safe_get(row, 0).replace("\n", "").replace("\r", "").strip()
            herb_name = safe_get(row, 1).replace("\n", " ").replace("\r", "").strip()
            if not code or not herb_name:
                continue

            item_id = str(uuid.uuid4())
            origin = safe_get(row, 2) or None
            grade = safe_get(row, 3) or None
            price_per_geun = parse_number(safe_get(row, 4))
            pkg_unit_g = parse_int(safe_get(row, 5))
            pkg_unit_price = parse_number(safe_get(row, 6))
            box_qty = parse_int(safe_get(row, 7))
            sub_price = parse_number(safe_get(row, 8))
            sub_unit_g = parse_int(safe_get(row, 9))
            sub_unit_price = parse_number(safe_get(row, 10))
            sub_box_qty = parse_int(safe_get(row, 11))
            manufacturer = safe_get(row, 12) or None
            note = safe_get(row, 13) or None
            discount_rate = safe_get(row, 14) or None

            lines.append(
                f"INSERT INTO herb_price_item "
                f"(id, code, herb_name, origin, grade, source_type, "
                f"price_per_geun, packaging_unit_g, packaging_unit_price, box_quantity, "
                f"subscription_price, subscription_unit_g, subscription_unit_price, subscription_box_qty, "
                f"manufacturer, note, discount_rate) VALUES ("
                f"'{item_id}', {sql_str(code)}, {sql_str(herb_name)}, {sql_str(origin)}, {sql_str(grade)}, "
                f"{sql_str(source_type)}, {sql_num(price_per_geun)}, {sql_num(pkg_unit_g)}, "
                f"{sql_num(pkg_unit_price)}, {sql_num(box_qty)}, {sql_num(sub_price)}, "
                f"{sql_num(sub_unit_g)}, {sql_num(sub_unit_price)}, {sql_num(sub_box_qty)}, "
                f"{sql_str(manufacturer)}, {sql_str(note)}, {sql_str(discount_rate)});"
            )
            total_items += 1

            # 월별 이력
            for reg_col, sub_col, year_month in MONTH_COLUMNS:
                reg_price = parse_number(safe_get(row, reg_col))
                sub_price_monthly = parse_number(safe_get(row, sub_col))
                if reg_price is not None or sub_price_monthly is not None:
                    hist_id = str(uuid.uuid4())
                    lines.append(
                        f"INSERT INTO herb_price_history "
                        f"(id, item_id, year_month, regular_price, subscription_price) VALUES ("
                        f"'{hist_id}', '{item_id}', '{year_month}', "
                        f"{sql_num(reg_price)}, {sql_num(sub_price_monthly)});"
                    )
                    total_hist += 1

        lines.append("")

    lines.append("COMMIT;")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"SQL 생성 완료: {OUTPUT}")
    print(f"항목: {total_items}, 월별 이력: {total_hist}")


if __name__ == "__main__":
    main()
