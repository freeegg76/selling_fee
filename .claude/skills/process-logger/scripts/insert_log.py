"""
처리 로그를 DB에 저장한다 (SP_Insert_Processing_Log).
로그 저장 실패는 전체 흐름을 막지 않는다.
"""
import argparse
import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


def find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


ROOT = find_project_root()
load_dotenv(ROOT / ".env")


def get_connection() -> pyodbc.Connection:
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER", "")
    database = os.getenv("DB_DATABASE", "")
    uid = os.getenv("DB_USER", "")
    pwd = os.getenv("DB_PASSWORD", "")

    trust = os.getenv("DB_TRUST_SERVER_CERT", "no")
    if uid and pwd:
        conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate={trust};"
    else:
        conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate={trust};"

    return pyodbc.connect(conn_str, timeout=10)


def insert_log(yyyymm: str, company_code: str, step: str, status: str, message: str) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "EXEC SP_Insert_Processing_Log @YYYYMM=?, @CompanyCode=?, @Step=?, @Status=?, @Message=?",
            (yyyymm, company_code, step, status, message),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"WARN: 로그 저장 실패 (스킵): {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yyyymm", required=True)
    parser.add_argument("--company_code", required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--status", required=True, choices=["SUCCESS", "FAILED", "PARTIAL", "SKIPPED"])
    parser.add_argument("--message", default="")
    args = parser.parse_args()

    ok = insert_log(args.yyyymm, args.company_code, args.step, args.status, args.message)
    if ok:
        print(f"[LOG] {args.company_code} | {args.step} | {args.status}")
    sys.exit(0)  # 로그 저장 실패도 0으로 반환 (흐름 유지)


if __name__ == "__main__":
    main()
