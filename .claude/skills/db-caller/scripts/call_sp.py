"""
SP caller - MS SQL Server 저장 프로시저 호출 래퍼.

Usage:
  python call_sp.py --sp SP_NAME --params '{"@PARAM": "value"}' [--output path.json]
"""
import argparse
import json
import os
import sys
from decimal import Decimal
from datetime import date, datetime
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
    trust_cert = os.getenv("DB_TRUST_SERVER_CERT", "no")

    if uid and pwd:
        conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate={trust_cert};"
    else:
        conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate={trust_cert};"

    return pyodbc.connect(conn_str, timeout=30)


def _serialize(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def call_sp(sp_name: str, params: dict) -> list:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if params:
            param_clause = ", ".join(f"@{k.lstrip('@')} = ?" for k in params)
            sql = f"EXEC {sp_name} {param_clause}"
            cursor.execute(sql, list(params.values()))
        else:
            cursor.execute(f"EXEC {sp_name}")

        if cursor.description is None:
            return []

        columns = [col[0] for col in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append({col: _serialize(val) for col, val in zip(columns, row)})
        return rows
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="MS SQL Server SP caller")
    parser.add_argument("--sp", required=True, help="저장 프로시저 이름")
    parser.add_argument("--params", default="{}", help='JSON 파라미터 (예: \'{"@YYYYMM": "202504"}\')')
    parser.add_argument("--output", default=None, help="결과 저장 경로 (생략 시 stdout)")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(f"ERROR: --params 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = call_sp(args.sp, params)
    except Exception as e:
        print(f"ERROR: SP 실행 실패 [{args.sp}]: {e}", file=sys.stderr)
        sys.exit(1)

    output_str = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_str, encoding="utf-8")
        print(f"저장 완료: {args.output} ({len(result)}건)")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
