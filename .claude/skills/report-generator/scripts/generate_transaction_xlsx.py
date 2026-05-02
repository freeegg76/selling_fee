"""
Transaction Report xlsx 생성기.

SP_Get_AmzOrder_By_Client 결과를 Transaction_Report 탭에 주입하여 xlsx로 내보낸다.
데이터 범위: Transaction_Report!B11:T (헤더 없이 데이터만)

Usage:
  python generate_transaction_xlsx.py --yyyymm 202504 --company_code ABC --base_dir output
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import get_sheets_and_drive, find_project_root

ROOT = find_project_root()
load_dotenv(ROOT / ".env")

TEMPLATE_ID = os.getenv("TEMPLATE_SPREADSHEET_ID", "192bh56QrTjBbv7Gwk9dkdRZRhBqr4hW70tZCqQOFtJY")
TAB_NAME = "Transaction_Report"
DATA_RANGE_START = "B11"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ── DB ───────────────────────────────────────────────────────────────────────

def _db_conn():
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER", "")
    db = os.getenv("DB_DATABASE", "")
    uid = os.getenv("DB_USER", "")
    pwd = os.getenv("DB_PASSWORD", "")
    trust = os.getenv("DB_TRUST_SERVER_CERT", "no")
    if uid and pwd:
        cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};TrustServerCertificate={trust};"
    else:
        cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate={trust};"
    return pyodbc.connect(cs, timeout=30)


def _call_sp(sp_name: str, params: dict) -> list:
    conn = _db_conn()
    try:
        cur = conn.cursor()
        clause = ", ".join(f"@{k.lstrip('@')} = ?" for k in params)
        cur.execute(f"EXEC {sp_name} {clause}", list(params.values()))
        if not cur.description:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


# ── Sheets / Drive 조작 ──────────────────────────────────────────────────────

def _copy_spreadsheet(drive, name: str) -> str:
    res = drive.files().copy(fileId=TEMPLATE_ID, body={"name": name}).execute()
    return res["id"]


def _delete_other_tabs(sheets, ss_id: str, keep_tab: str):
    meta = sheets.spreadsheets().get(spreadsheetId=ss_id).execute()
    reqs = [
        {"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}
        for s in meta["sheets"]
        if s["properties"]["title"] != keep_tab
    ]
    if reqs:
        sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body={"requests": reqs}).execute()


def _find_replace(sheets, ss_id: str, replacements: dict):
    reqs = [
        {
            "findReplace": {
                "find": ph,
                "replacement": str(val) if val is not None else "",
                "allSheets": True,
                "matchCase": True,
                "matchEntireCell": False,
                "includeFormulas": False,
            }
        }
        for ph, val in replacements.items()
    ]
    if reqs:
        sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body={"requests": reqs}).execute()


def _write_data(sheets, ss_id: str, data_range: str, rows: list):
    sheets.spreadsheets().values().update(
        spreadsheetId=ss_id,
        range=data_range,
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()


def _export_xlsx(drive, ss_id: str, out_path: str):
    content = drive.files().export(fileId=ss_id, mimeType=XLSX_MIME).execute()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(content)


def _delete_ss(drive, ss_id: str):
    drive.files().delete(fileId=ss_id).execute()


def _safe_str(v) -> str:
    if v is None:
        return ""
    return str(v)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yyyymm", required=True)
    parser.add_argument("--company_code", required=True)
    parser.add_argument("--base_dir", default="output")
    parser.add_argument("--output")
    args = parser.parse_args()

    base = Path(args.base_dir) / args.yyyymm / args.company_code
    out_path = args.output or str(base / "transaction_report.xlsx")

    # 고객사 주문 데이터 조회
    orders = _call_sp(
        "SP_Get_AmzOrder_By_Client",
        {"@YYYYMM": args.yyyymm, "@CompanyCode": args.company_code},
    )

    if not orders:
        print(f"WARN: 주문 데이터 없음 ({args.company_code})", file=sys.stderr)

    # 고객사 기본 정보
    clients = _call_sp("SP_Get_Client_Info", {"@CompanyCode": args.company_code})
    client = clients[0] if clients else {}

    # 데이터 행 구성 (SP 컬럼 순서 그대로 B11:T에 기록)
    data_rows = []
    if orders:
        columns = list(orders[0].keys())
        for row in orders:
            data_rows.append([_safe_str(row.get(c)) for c in columns])

    # 플레이스홀더
    replacements = {
        "[회사명]": client.get("company_name", ""),
        "[주소]": client.get("address", ""),
        "[사업자번호]": client.get("business_number", ""),
        "[대표자명]": client.get("representative", ""),
    }

    # 생성
    sheets, drive = get_sheets_and_drive()
    temp_name = f"_temp_txreport_{args.company_code}_{args.yyyymm}"
    temp_id = _copy_spreadsheet(drive, temp_name)

    try:
        _delete_other_tabs(sheets, temp_id, TAB_NAME)
        _find_replace(sheets, temp_id, replacements)
        if data_rows:
            _write_data(sheets, temp_id, DATA_RANGE_START, data_rows)
        _export_xlsx(drive, temp_id, out_path)
        print(f"Transaction Report 생성 완료: {out_path} ({len(data_rows)}행)")
    except Exception as e:
        print(f"ERROR: Transaction Report 생성 실패: {e}", file=sys.stderr)
        raise
    finally:
        try:
            _delete_ss(drive, temp_id)
        except Exception:
            pass


if __name__ == "__main__":
    main()
