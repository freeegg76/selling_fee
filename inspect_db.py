"""DB 객체 구조 확인 스크립트."""
import sys, os
from pathlib import Path
ROOT = Path(r"c:\Dev\SellingFee")
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "db-caller" / "scripts"))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
import pyodbc, os

driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
server = os.getenv("DB_SERVER", "")
db     = os.getenv("DB_DATABASE", "")
uid    = os.getenv("DB_USER", "")
pwd    = os.getenv("DB_PASSWORD", "")
trust  = os.getenv("DB_TRUST_SERVER_CERT", "no")
if uid and pwd:
    cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};TrustServerCertificate={trust};"
else:
    cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate={trust};"

conn = pyodbc.connect(cs, timeout=30)
cur  = conn.cursor()

# 1. SP 정의
print("="*70)
print("SP_Convert_Order_Amount_To_USD 정의")
print("="*70)
cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID('SP_Convert_Order_Amount_To_USD'))")
row = cur.fetchone()
print(row[0] if row else "NOT FOUND")

# 2. ConvertFx 테이블 컬럼
print("\n" + "="*70)
print("ConvertFx 테이블 구조")
print("="*70)
cur.execute("""
    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'ConvertFx'
    ORDER BY ORDINAL_POSITION
""")
for r in cur.fetchall():
    print(r)

# 3. ConvertFx 샘플 데이터
print("\n" + "="*70)
print("ConvertFx 샘플 데이터 (최대 10건)")
print("="*70)
cur.execute("SELECT TOP 10 * FROM ConvertFx ORDER BY 1 DESC")
cols = [c[0] for c in cur.description]
print(cols)
for r in cur.fetchall():
    print(list(r))

conn.close()
