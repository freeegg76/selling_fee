"""
Transaction Report xlsx 생성기.

SP_Get_AmzOrder_By_Client 결과를 Transaction_Report 탭에 주입하여 xlsx로 내보낸다.
데이터 범위: Transaction_Report!B11 ~ (헤더 없이 데이터만)
Performance 열은 SP_Get_OrderMeasure_By_Client 룰 기반으로 산정하여 마지막 열(U)에 추가한다.
비USD 통화 주문은 orders_usd.json의 *USD 필드(SP_Convert_Order_Amount_To_USD → ConvertFx 기반)로 환산한다.

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

# OrderMeasure 테이블의 가산/차감 대상 필드 (원본 → USD 변환 필드 쌍)
_MEASURE_FIELD_USD = [
    ("ItemPrice",             "ItemPriceUSD"),
    ("ItemTax",               "ItemTaxUSD"),
    ("ShippingPrice",         "ShippingPriceUSD"),
    ("ShippingTax",           "ShippingTaxUSD"),
    ("GiftWrapPrice",         "GiftWrapPriceUSD"),
    ("GiftWrapTax",           "GiftWrapTaxUSD"),
    ("ItemPromotionDiscount", "ItemPromotionDiscountUSD"),
    ("ShipPromotionDiscount", "ShipPromotionDiscountUSD"),
]
# 원본 필드명 목록 (열 순서 유지용)
MEASURE_FIELDS = [f[0] for f in _MEASURE_FIELD_USD]

# 템플릿 열 레이아웃: (orders_usd 필드명, 숫자여부)
# B~T (첫 열 name_eng skip), U = Performance (마지막 추가)
_TEMPLATE_COLUMNS = [
    ("AmazonOrderId",          False),  # B
    ("MerchantOrderId",        False),  # C
    ("PurchaseDate",           False),  # D
    ("OrderStatus",            False),  # E
    ("SKU",                    False),  # F
    ("ASIN",                   False),  # G
    ("Quantity",               True),   # H
    ("Currency",               False),  # I
    ("RateToUSD",              True),   # J: ConvertFx 환율 (FXRate 대체)
    ("ItemPrice",              True),   # K
    ("ItemTax",                True),   # L
    ("ShippingPrice",          True),   # M
    ("ShippingTax",            True),   # N
    ("GiftWrapPrice",          True),   # O
    ("GiftWrapTax",            True),   # P
    ("ItemPromotionDiscount",  True),   # Q
    ("ShipPromotionDiscount",  True),   # R
    ("ShipCity",               False),  # S
    ("PromotionIds",           False),  # T
]

# 행 높이 설정 (row_index 0-based, pixel_size)
ROW_HEIGHTS = [
    (1, 76),   # 2번 행: 57.00pt / 76px
    (9, 46),   # 10번 행: 34.50pt / 46px
]


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


# ── Performance 계산 ──────────────────────────────────────────────────────────

def _calc_performance(order: dict, measure: dict, usd_row: dict = None) -> float:
    """OrderMeasure 룰(+/-/NULL)에 따라 트랜잭션별 PerformanceUSD를 산정한다.

    비USD 통화는 usd_row의 *USD 필드(ConvertFx 기반 환산값)를 우선 사용한다.
    usd_row가 없거나 *USD가 null이면 USD 주문에 한해 원본 금액을 그대로 사용한다.
    """
    usd_row = usd_row or {}
    is_usd = (order.get("Currency") or "USD").upper() == "USD"
    total = 0.0
    for orig_field, usd_field in _MEASURE_FIELD_USD:
        sign = measure.get(orig_field)
        if not sign:
            continue
        usd_val = usd_row.get(usd_field)
        if usd_val is not None:
            val = float(usd_val)
        elif is_usd:
            val = float(order.get(orig_field) or 0)
        else:
            val = 0.0  # 비USD이고 *USD도 없으면 0 (환율 미등록 통화)
        if sign == "+":
            total += val
        elif sign == "-":
            total -= val
    return round(total, 6)


# ── 값 변환 ───────────────────────────────────────────────────────────────────

def _safe_str(v) -> str:
    if v is None:
        return ""
    return str(v)


def _to_num(v):
    """숫자 열 값을 float으로 변환. 변환 불가 시 문자열 반환."""
    if v is None:
        return None
    try:
        f = float(str(v).replace(",", ""))
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return _safe_str(v)


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


def _get_sheet_id(sheets, ss_id: str, tab_name: str) -> int:
    meta = sheets.spreadsheets().get(spreadsheetId=ss_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{tab_name}' not found")


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


def _col_letter(idx: int) -> str:
    """0-based 열 인덱스를 열 문자로 변환. A=0, B=1, Z=25, AA=26 ..."""
    result = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        result = chr(65 + r) + result
    return result


def _set_row_heights(sheets, ss_id: str, sheet_id: int, heights: list):
    """heights: [(row_index_0based, pixel_size), ...] 를 한 번에 설정한다."""
    reqs = [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": ri,
                    "endIndex": ri + 1,
                },
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        }
        for ri, px in heights
    ]
    sheets.spreadsheets().batchUpdate(spreadsheetId=ss_id, body={"requests": reqs}).execute()


def _export_xlsx(drive, ss_id: str, out_path: str):
    content = drive.files().export(fileId=ss_id, mimeType=XLSX_MIME).execute()
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
    out_path = args.output or str(base / "transaction_report.xlsx")

    # USD 환산 데이터 로드 (orders_usd.json 우선, 없으면 SP 직접 호출)
    # orders_usd를 단일 데이터 소스로 사용: 원본 금액 + *USD 변환값 + RateToUSD 포함
    orders_usd_path = base / "orders_usd.json"
    if orders_usd_path.exists():
        with open(orders_usd_path, encoding="utf-8") as f:
            orders_usd = json.load(f)
    else:
        orders_usd = _call_sp(
            "SP_Convert_Order_Amount_To_USD",
            {"@YYYYMM": args.yyyymm, "@CompanyCode": args.company_code},
        )

    if not orders_usd:
        print(f"WARN: 주문 데이터 없음 ({args.company_code})", file=sys.stderr)

    # OrderMeasure 조회 (Performance 산정 룰: +/-/NULL)
    measures = _call_sp("SP_Get_OrderMeasure_By_Client", {"@CompanyCode": args.company_code})
    measure = measures[0] if measures else {}

    # 고객사 기본 정보
    clients = _call_sp("SP_Get_Client_Info", {"@CompanyCode": args.company_code})
    client = clients[0] if clients else {}

    # 데이터 행 구성: _TEMPLATE_COLUMNS 레이아웃으로 orders_usd 직접 사용
    # J열(RateToUSD)은 ConvertFx 기반 실제 환율, Performance는 *USD 필드로 정확 계산
    data_rows = []
    for row in orders_usd:
        vals = []
        for field, is_num in _TEMPLATE_COLUMNS:
            v = row.get(field)
            vals.append(_to_num(v) if is_num else _safe_str(v))
        vals.append(_calc_performance(row, measure, row))  # row 자체에 *USD 필드 포함
        data_rows.append(vals)

    # Performance 헤더 셀 (U열)
    perf_col = _col_letter(1 + len(_TEMPLATE_COLUMNS))
    perf_header_range = f"{perf_col}10"

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
        sheet_id = _get_sheet_id(sheets, temp_id, TAB_NAME)
        _find_replace(sheets, temp_id, replacements)
        if data_rows:
            _write_data(sheets, temp_id, DATA_RANGE_START, data_rows)
        _write_data(sheets, temp_id, perf_header_range, [["Performance"]])
        _set_row_heights(sheets, temp_id, sheet_id, ROW_HEIGHTS)
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
