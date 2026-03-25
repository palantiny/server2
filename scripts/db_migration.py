import sqlite3
import os
import re
import pandas as pd  # pylint: disable=import-error
from sqlalchemy import create_engine  # pylint: disable=import-error

# ==========================================
# 1. 파일 경로 및 DB 세팅 (raw_data 폴더 기준)
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'raw_data')

SCHEMA_FILE = os.path.join(DATA_DIR, 'djmedi_medicine_scheme.sql')
SQL_DATA_FILES = [
    os.path.join(DATA_DIR, 'djmedi_maker_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicine_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicine_dj_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicineNHIS_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_medicineuse_data.sql'),
    os.path.join(DATA_DIR, 'djmedi_warehouse_data.sql')
]

CSV_DOMESTIC_FILE = os.path.join(DATA_DIR, '(원외탕전실용)한약재가격표종합 - 국산.csv')
CSV_IMPORTED_FILE = os.path.join(DATA_DIR, '(원외탕전실용)한약재가격표종합 - 수입.csv')

PG_DB_URL = "postgresql://palantiny:palantiny_secret@localhost:5432/palantiny_db"

STAGING_DB = os.path.join(BASE_DIR, 'temp_staging.db')

# ==========================================
# 2. 파서 및 클리너 함수
# ==========================================
def clean_sql_for_sqlite(sql_text):
    # 백틱 제거 (MySQL 식별자 → SQLite 표준 식별자)
    sql_text = re.sub(r'`', '', sql_text)

    # 컬럼 수준 COMMENT 제거 (주석 안의 특수문자까지 포함)
    sql_text = re.sub(r"\s+COMMENT\s+'[^']*'", '', sql_text, flags=re.IGNORECASE)

    # 컬럼 수준 COLLATE 제거
    sql_text = re.sub(r"\s+COLLATE\s+'[^']*'", '', sql_text, flags=re.IGNORECASE)

    # AUTO_INCREMENT 제거 (SQLite는 INTEGER PRIMARY KEY가 자동 auto-increment)
    sql_text = re.sub(r'\s+AUTO_INCREMENT', '', sql_text, flags=re.IGNORECASE)

    # CREATE TABLE 내부의 INDEX / FULLTEXT INDEX 라인 제거 (라인별 처리)
    filtered_lines = []
    for line in sql_text.splitlines():
        if re.match(r'^\s*(FULLTEXT\s+)?INDEX\s+', line, re.IGNORECASE):
            continue
        filtered_lines.append(line)
    sql_text = '\n'.join(filtered_lines)

    # PRIMARY KEY의 USING BTREE/HASH 제거
    sql_text = re.sub(r'\s+USING\s+(BTREE|HASH)', '', sql_text, flags=re.IGNORECASE)

    # INT(n) → INTEGER (SQLite auto-increment은 INTEGER 타입 필요)
    sql_text = re.sub(r'\bINT\s*\(\d+\)', 'INTEGER', sql_text, flags=re.IGNORECASE)

    # DEFAULT '숫자' → DEFAULT 숫자 (따옴표 제거)
    sql_text = re.sub(r"DEFAULT\s+'(\d+\.?\d*)'", r'DEFAULT \1', sql_text, flags=re.IGNORECASE)

    # 테이블 수준 옵션 제거 (ENGINE=, ROW_FORMAT=, COLLATE=, COMMENT=)
    sql_text = re.sub(r'\bENGINE\s*=\s*\w+', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r'\bROW_FORMAT\s*=\s*\w+', '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"COLLATE\s*=\s*'[^']*'", '', sql_text, flags=re.IGNORECASE)
    sql_text = re.sub(r"COMMENT\s*=\s*'[^']*'", '', sql_text, flags=re.IGNORECASE)

    # INDEX 제거 후 생긴 닫는 괄호 직전의 trailing comma 정리
    sql_text = re.sub(r',(\s*\))', r'\1', sql_text)

    return sql_text

def execute_sql_file(cursor, filepath):
    print(f"⏳ 스테이징 중: {os.path.basename(filepath)} ...")
    with open(filepath, 'r', encoding='utf-8') as f:
        sql_script = f.read()
        sql_script = clean_sql_for_sqlite(sql_script)
        cursor.executescript(sql_script)

# ==========================================
# 3. 메인 마이그레이션 로직
# ==========================================
def main():
    if os.path.exists(STAGING_DB):
        os.remove(STAGING_DB)
        
    sqlite_conn = sqlite3.connect(STAGING_DB)
    sqlite_cursor = sqlite_conn.cursor()
    pg_engine = create_engine(PG_DB_URL)

    try:
        print("🚀 [STEP 1] SQL 파일을 임시 메모리에 적재하여 정제...")
        execute_sql_file(sqlite_cursor, SCHEMA_FILE)
        for sql_file in SQL_DATA_FILES:
            execute_sql_file(sqlite_cursor, sql_file)

        print("\n🚀 [STEP 2] 정제된 데이터를 PostgreSQL로 전송...")
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in sqlite_cursor.fetchall() if row[0] != 'sqlite_sequence']

        for table in tables:
            df = pd.read_sql_query(f"SELECT * FROM {table}", sqlite_conn)
            df.to_sql(table, con=pg_engine, if_exists='replace', index=False)
            print(f"  ✅ DB 이관 완료: '{table}' (총 {len(df)}행)")

        print("\n🚀 [STEP 3] 가격표 CSV 파일을 읽어 PostgreSQL에 적재...")
        df_domestic = pd.read_csv(CSV_DOMESTIC_FILE, encoding='utf-8-sig')
        df_domestic.to_sql('price_domestic', con=pg_engine, if_exists='replace', index=False)
        print(f"  ✅ DB 이관 완료: 'price_domestic' (총 {len(df_domestic)}행)")
        
        df_imported = pd.read_csv(CSV_IMPORTED_FILE, encoding='utf-8-sig')
        df_imported.to_sql('price_imported', con=pg_engine, if_exists='replace', index=False)
        print(f"  ✅ DB 이관 완료: 'price_imported' (총 {len(df_imported)}행)")

    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
    finally:
        sqlite_conn.close()
        pg_engine.dispose()
        if os.path.exists(STAGING_DB):
            os.remove(STAGING_DB)
        print("\n🎉 모든 데이터 마이그레이션 작업이 완료되었습니다!")

if __name__ == "__main__":
    main()