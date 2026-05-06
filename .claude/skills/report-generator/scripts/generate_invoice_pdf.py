"""
Invoice PDF 생성기.

output/{YYYYMM}/{company_code}/ 하위의 JSON 파일을 읽고
Google Sheets 템플릿을 이용하여 invoice.pdf를 생성한다.

Usage:
  python generate_invoice_pdf.py --yyyymm 202504 --company_code ABC --base_dir output
"""
import argparse
import calendar
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import get_sheets_and_drive, find_project_root

ROOT = find_project_root()
load_dotenv(ROOT / ".env")

TEMPLATE_ID = os.getenv("TEMPLATE_SPREADSHEET_ID", "192bh56QrTjBbv7Gwk9dkdRZRhBqr4hW70tZCqQOFtJY")

TAB_NAMES = {"KRW": "Invoice_Template_KRW", "USD": "Invoice_Template_USD"}


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


# ── 날짜 헬퍼 ─────────────────────────────────────────────────────────────────

def _dates(yyyymm: str):
    y, m = int(yyyymm[:4]), int(yyyymm[4:6])
    first = date(y, m, 1)
    last = date(y, m, calendar.monthrange(y, m)[1])
    due = first + timedelta(days=14)
    next_m = m % 12 + 1
    next_y = y + (1 if m == 12 else 0)
    invoice_date = date(next_y, next_m, 1)
    return first, last, due, invoice_date


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


def _export_pdf(drive, ss_id: str, out_path: str):
    content = drive.files().export(fileId=ss_id, mimeType="application/pdf").execute()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(content)


def _delete_ss(drive, ss_id: str):
    drive.files().delete(fileId=ss_id).execute()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yyyymm", required=True)
    parser.add_argument("--company_code", required=True)
    parser.add_argument("--base_dir", default="output")
    parser.add_argument("--output")
    args = parser.parse_args()

    base = Path(args.base_dir) / args.yyyymm / args.company_code
    out_path = args.output or str(base / "invoice.pdf")

    # JSON 로드
    billing_raw = json.loads((base / "billing.json").read_text(encoding="utf-8"))
    billing = billing_raw[0] if isinstance(billing_raw, list) else billing_raw
    selling_fee_raw = json.loads((base / "selling_fee.json").read_text(encoding="utf-8"))

    currency = billing.get("BillingCurrency", "KRW")
    tab = TAB_NAMES.get(currency, TAB_NAMES["KRW"])

    # 고객사 정보 (DB)
    clients = _call_sp("SP_Get_Client_Info", {"@CompanyCode": args.company_code})
    if not clients:
        print(f"ERROR: 고객사 정보 없음: {args.company_code}", file=sys.stderr)
        sys.exit(1)
    client = clients[0]

    # 날짜 계산
    first, last, due, invoice_date = _dates(args.yyyymm)
    alias = client.get("alias") or args.company_code
    inv_no = f"{alias}_invoice_amz_selling_{args.yyyymm[:4]}-{args.yyyymm[4:6]}"

    # 적용 요율: selling_fee.json에서 실제 적용된 구간(AppliedAmountUSD > 0)의 요율만 연결
    rate_str = ", ".join(
        f"{float(r['rate']) * 100:.4g}%"
        for r in selling_fee_raw
        if (r.get("AppliedAmountUSD") or 0) > 0
    )

    replacements = {
        "[회사명]": client.get("company_name", ""),
        "[주소]": client.get("address", ""),
        "[사업자번호]": client.get("business_number", ""),
        "[대표자명]": client.get("representative", ""),
        "[인보이스 청구년월]": f"{args.yyyymm[:4]}/{args.yyyymm[4:6]}",
        "[인보이스번호]": inv_no,
        "[인보이스일자]": invoice_date.strftime("%Y/%m/%d"),
        "[지급기한]": str(due),
        "[서비스 기간]": f"{first} ~ {last}",
        "[주문 실적]": f"{float(billing.get('PerformanceUSD', 0)):,.2f}",
        "[적용 요율]": rate_str,
        "[셀링피]": f"{float(billing.get('SellingFeeUSD', 0)):,.2f}",
    }

    if currency == "KRW":
        replacements["[USD to KRW 환율]"] = f"{float(billing.get('USDKRWRate', 0)):,.2f}"

    # 생성
    sheets, drive = get_sheets_and_drive()
    temp_name = f"_temp_invoice_{args.company_code}_{args.yyyymm}"
    temp_id = _copy_spreadsheet(drive, temp_name)

    try:
        _delete_other_tabs(sheets, temp_id, tab)
        _find_replace(sheets, temp_id, replacements)
        _export_pdf(drive, temp_id, out_path)
        print(f"Invoice PDF 생성 완료: {out_path}")
    except Exception as e:
        print(f"ERROR: Invoice 생성 실패: {e}", file=sys.stderr)
        raise
    finally:
        try:
            _delete_ss(drive, temp_id)
        except Exception:
            pass


if __name__ == "__main__":
    main()
