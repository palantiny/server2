"""
data/herb_price_korea.csv, data/herb_price_foreign.csv → Neo4j MERGE Cypher.

CSV는 3행 멀티헤더(header=[0,1,2]) 형식(원외탕전실용 가격표)을 가정한다.

실행 (프로젝트 루트):
  python scripts/herb_prices_to_cypher.py
  python scripts/herb_prices_to_cypher.py -o scripts/out.cypher
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_price(val):
    """가격을 파싱하여 (Cypher용 숫자문자열, 상태) 형태로 반환."""
    if pd.isna(val) or str(val).strip() == "":
        return "null", "정보없음"

    val_str = str(val).strip().replace(",", "")
    if val_str.isdigit():
        return val_str, "정상"
    return "null", val_str


def escape_cypher_str(val: str) -> str:
    """단일 인용부호로 감쌀 문자열 이스케이프."""
    s = str(val)
    return s.replace("\\", "\\\\").replace("'", "\\'")


def clean_str(val, default: str = "") -> str:
    """빈값 처리 및 Cypher용 이스케이프."""
    if pd.isna(val) or str(val).strip() == "":
        return default
    return escape_cypher_str(str(val).strip().replace("\n", " ").replace("\r", ""))


_MONTH_26 = re.compile(r"26년\s*(\d{1,2})\s*월")
_MONTH_ONLY = re.compile(r"^(\d{1,2})\s*월$")


def month_key_from_level0(level0) -> str | None:
    """멀티인덱스 level0 문자열 → 'YYYY-MM'."""
    s = str(level0).strip()
    if not s or s.lower() == "nan" or "Unnamed" in s or s == "2025":
        return None
    m = _MONTH_26.search(s)
    if m:
        return f"2026-{int(m.group(1)):02d}"
    m = _MONTH_ONLY.match(s)
    if m:
        return f"2025-{int(m.group(1)):02d}"
    return None


def _is_general_geundang_col(col: tuple) -> bool:
    """일반 구매 근당가 열만 (구독 열 제외). 당월 열은 '일반 구매'가 level0에만 있는 경우가 있다."""
    if "근당" not in str(col[2]):
        return False
    if "구독" in str(col[1]):
        return False
    return "일반 구매" in str(col[0]) or "일반 구매" in str(col[1])


def build_month_columns(
    df: pd.DataFrame,
    *,
    current_month_key: str = "2026-03",
) -> dict[str, tuple]:
    """일반 구매 근당가 컬럼만 모아 월 → 컬럼 튜플.

    표 상단 당월(예: 26년 3월) 근당 열은 level0이 '일반 구매'로만 잡혀 월 키가 없으므로,
    그런 첫 열을 current_month_key 로 넣는다.
    """
    month_columns: dict[str, tuple] = {}
    filled_current = False
    for col in df.columns:
        if not _is_general_geundang_col(col):
            continue
        mk = month_key_from_level0(col[0])
        if mk:
            month_columns[mk] = col
            continue
        if not filled_current:
            month_columns[current_month_key] = col
            filled_current = True
    return month_columns


def get_col(df: pd.DataFrame, search_term: str):
    for col in df.columns:
        if search_term in str(col[2]):
            return col
    return None


def generate_cypher_file(
    file_paths_and_origins: list[tuple[Path, str]],
    output_path: Path,
    *,
    current_month_key: str = "2026-03",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with open(output_path, "a", encoding="utf-8") as f:
        f.write("// ==========================================================\n")
        f.write("// 팔란티니 지식 그래프 — 가격 CSV → Cypher (Commerce)\n")
        f.write("// ==========================================================\n\n")

        for file_path, origin_category in file_paths_and_origins:
            print(f"[{file_path.name}] 변환 중...")
            df = pd.read_csv(file_path, header=[0, 1, 2], encoding="utf-8-sig")

            col_code = get_col(df, "코드")
            col_herb = get_col(df, "약재명")
            col_origin = get_col(df, "원산지")
            col_type = get_col(df, "구분")
            col_pack_unit = get_col(df, "포장 단위(g)")
            col_pack_price = get_col(df, "포장 단위 당 가격")
            col_box_qty = get_col(df, "박스 수량")
            col_maker = get_col(df, "제약사")

            required = {
                "코드": col_code,
                "약재명": col_herb,
                "원산지": col_origin,
                "구분": col_type,
                "포장 단위(g)": col_pack_unit,
                "포장 단위 당 가격": col_pack_price,
                "박스 수량": col_box_qty,
                "제약사": col_maker,
            }
            missing = [k for k, v in required.items() if v is None]
            if missing:
                print(f"  [오류] 컬럼 없음: {missing}", file=sys.stderr)
                raise SystemExit(1)

            month_columns = build_month_columns(df, current_month_key=current_month_key)
            if not month_columns:
                print("  [경고] 월별 일반 구매 근당 가격 컬럼을 찾지 못했습니다.", file=sys.stderr)

            success_count = 0
            for _idx, row in df.iterrows():
                herb_name = clean_str(row[col_herb])
                if not herb_name:
                    continue

                product_id = clean_str(row[col_code])
                if not product_id:
                    continue

                origin_val = clean_str(row[col_origin], default=origin_category)
                maker_val = clean_str(row[col_maker], default="제약사 미상")
                type_val = clean_str(row[col_type], default="일반")
                pack_unit = clean_str(row[col_pack_unit])
                pack_price = clean_str(row[col_pack_price])
                box_qty = clean_str(row[col_box_qty])

                cypher = f"// --- [{product_id}] {herb_name} ({maker_val}) ---\n"
                cypher += f"MERGE (m:Maker {{name: '{maker_val}'}})\n"
                cypher += f"MERGE (o:Origin {{name: '{origin_val}'}})\n"
                cypher += f"MERGE (p:Product {{product_id: '{product_id}'}})\n"

                set_props = (
                    f"p.type = '{type_val}', p.pack_unit = '{pack_unit}', "
                    f"p.pack_price = '{pack_price}', p.box_qty = '{box_qty}'"
                )
                cypher += f"ON CREATE SET {set_props}\n"
                cypher += f"ON MATCH SET {set_props}\n"

                cypher += "MERGE (p)-[:MANUFACTURED_BY]->(m)\n"
                cypher += "MERGE (p)-[:ORIGINATES_FROM]->(o)\n"
                cypher += f"MERGE (h:Herb {{name: '{herb_name}'}})\n"
                cypher += "MERGE (h)-[:HAS_PRODUCT]->(p)\n"

                for month, col in sorted(month_columns.items()):
                    price_val, status = parse_price(row[col])
                    status_esc = escape_cypher_str(status)
                    pr_var = f"pr_{month.replace('-', '_')}"

                    cypher += (
                        f"MERGE ({pr_var}:PriceRecord "
                        f"{{month: '{month}', product_id: '{product_id}'}})\n"
                    )
                    cypher += (
                        f"ON CREATE SET {pr_var}.price_per_geun = {price_val}, "
                        f"{pr_var}.status = '{status_esc}'\n"
                    )
                    cypher += (
                        f"ON MATCH SET {pr_var}.price_per_geun = {price_val}, "
                        f"{pr_var}.status = '{status_esc}'\n"
                    )
                    cypher += f"MERGE (p)-[:HAS_PRICE_HISTORY]->({pr_var})\n"

                cypher += ";\n\n"
                f.write(cypher)
                success_count += 1

            print(f"  → {success_count}행 기록\n")

    print(f"완료: {output_path}")


def main() -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="한약재 가격 CSV → Cypher")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=root / "scripts" / "herb_prices_from_csv.cypher",
        help="출력 .cypher 경로",
    )
    parser.add_argument(
        "--current-month",
        default="2026-03",
        metavar="YYYY-MM",
        help="표 상단 당월 근당가 열에 붙일 월 키 (기본: 2026-03)",
    )
    args = parser.parse_args()

    files_to_process: list[tuple[Path, str]] = [
        (root / "data" / "herb_price_korea.csv", "한국"),
        (root / "data" / "herb_price_foreign.csv", "수입"),
    ]
    for p, _ in files_to_process:
        if not p.is_file():
            print(f"[오류] 파일 없음: {p}", file=sys.stderr)
            return 1

    generate_cypher_file(
        files_to_process,
        args.output.resolve(),
        current_month_key=args.current_month,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
