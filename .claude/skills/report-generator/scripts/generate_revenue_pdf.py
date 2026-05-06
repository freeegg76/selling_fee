"""
Revenue Report PDF 생성기.

SP_Get_AmzOrder_By_Client 결과를 ASIN별로 집계하여 Revenue_Report 탭에 주입 후 PDF 내보내기.
데이터 범위: Revenue_Report!A20:E (name_eng, ASIN, QTY, Revenue USD, 빈 열)

Usage:
  python generate_revenue_pdf.py --yyyymm 202504 --company_code ABC --base_dir output
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pyodbc
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from google_auth import get_sheets_and_drive, find_project_root

ROOT = find_project_root()
load_dotenv(ROOT / ".env")

TEMPLATE_ID = os.getenv("TEMPLATE_SPREADSHEET_ID", "192bh56QrTjBbv7Gwk9dkdRZRhBqr4hW70tZCqQOFtJY")
TAB_NAME = "Revenue_Report"
DATA_RANGE_START = "A20"


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


# ── ASIN 집계 ────────────────────────────────────────────────────────────────

_MEASURE_FIELDS = [
    ("ItemPrice",             "ItemPriceUSD"),
    ("ItemTax",               "ItemTaxUSD"),
    ("ShippingPrice",         "ShippingPriceUSD"),
    ("ShippingTax",           "ShippingTaxUSD"),
    ("GiftWrapPrice",         "GiftWrapPriceUSD"),
    ("GiftWrapTax",           "GiftWrapTaxUSD"),
    ("ItemPromotionDiscount", "ItemPromotionDiscountUSD"),
    ("ShipPromotionDiscount", "ShipPromotionDiscountUSD"),
]


def _calc_order_performance(row: dict, measure: dict) -> float:
    """OrderMeasure 룰에 따라 주문 1건의 PerformanceUSD 계산."""
    is_usd = (row.get("Currency") or "USD").upper() == "USD"
    total = 0.0
    for orig_field, usd_field in _MEASURE_FIELDS:
        sign = measure.get(orig_field)
        if not sign:
            continue
        usd_val = row.get(usd_field)
        if usd_val is not None:
            val = float(usd_val)
        elif is_usd:
            val = float(row.get(orig_field) or 0)
        else:
            val = 0.0  # non-USD 환율 없음 → SP와 동일하게 0 처리
        if sign == "+":
            total += val
        elif sign == "-":
            total -= val
    return total


def _get_product_names(skus: list) -> dict:
    """SKU 목록으로 products 테이블에서 name_eng 조회. {sku: name_eng} 반환."""
    if not skus:
        return {}
    conn = _db_conn()
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" * len(skus))
        cur.execute(f"SELECT sku, name_eng FROM products WHERE sku IN ({placeholders})", skus)
        return {row[0]: row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def _aggregate_by_asin(orders: list, measure: dict, product_names: dict) -> list:
    """ASIN별 QTY·Revenue(USD) 집계. 첫 컬럼은 products.name_eng."""
    data: dict = defaultdict(lambda: {"qty": 0, "revenue_usd": 0.0, "sku": ""})

    for row in orders:
        asin = str(row.get("ASIN") or "")
        sku = str(row.get("SKU") or "")
        qty = int(row.get("Quantity") or 0)
        rev = _calc_order_performance(row, measure)

        data[asin]["qty"] += qty
        data[asin]["revenue_usd"] += rev
        if not data[asin]["sku"] and sku:
            data[asin]["sku"] = sku

    return [
        [product_names.get(d["sku"], ""), asin, d["qty"], round(d["revenue_usd"], 2), ""]
        for asin, d in sorted(data.items())
    ]


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
    out_path = args.output or str(base / "revenue_report.pdf")

    # 주문 데이터 (STEP 3에서 생성된 orders_usd.json 우선 사용)
    orders_usd_path = base / "orders_usd.json"
    if orders_usd_path.exists():
        with open(orders_usd_path, encoding="utf-8") as f:
            orders = json.load(f)
    else:
        orders = _call_sp(
            "SP_Get_AmzOrder_By_Client",
            {"@YYYYMM": args.yyyymm, "@CompanyCode": args.company_code},
        )

    # 고객사 정보
    clients = _call_sp("SP_Get_Client_Info", {"@CompanyCode": args.company_code})
    client = clients[0] if clients else {}

    # OrderMeasure 룰 조회
    measures = _call_sp("SP_Get_OrderMeasure_By_Client", {"@CompanyCode": args.company_code})
    measure = measures[0] if measures else {}

    # SKU → name_eng 조회
    skus = list({str(r.get("SKU") or "") for r in orders if r.get("SKU")})
    product_names = _get_product_names(skus)

    # ASIN 집계
    asin_data = _aggregate_by_asin(orders, measure, product_names)

    replacements = {
        "[회사명]": client.get("company_name", ""),
        "[주소]": client.get("address", ""),
        "[사업자번호]": client.get("business_number", ""),
        "[대표자명]": client.get("representative", ""),
        "[별칭]": client.get("alias", ""),
        "[YYYYMM]": args.yyyymm,
        "YYYYMM": args.yyyymm,
    }

    sheets, drive = get_sheets_and_drive()
    temp_name = f"_temp_revreport_{args.company_code}_{args.yyyymm}"
    temp_id = _copy_spreadsheet(drive, temp_name)

    try:
        _delete_other_tabs(sheets, temp_id, TAB_NAME)
        _find_replace(sheets, temp_id, replacements)
        if asin_data:
            _write_data(sheets, temp_id, DATA_RANGE_START, asin_data)
        _export_pdf(drive, temp_id, out_path)
        print(f"Revenue Report 생성 완료: {out_path} (ASIN {len(asin_data)}종)")
    except Exception as e:
        print(f"ERROR: Revenue Report 생성 실패: {e}", file=sys.stderr)
        raise
    finally:
        try:
            _delete_ss(drive, temp_id)
        except Exception:
            pass


if __name__ == "__main__":
    main()
