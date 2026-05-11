"""
Transaction Report xlsx 생성기.

SP_Get_AmzOrder_By_Client 결과를 Transaction_Report 탭에 주입하여 xlsx로 내보낸다.
데이터 범위: Transaction_Report!B11 ~ (헤더 없이 데이터만)
Performance 열은 SP_Get_OrderMeasure_By_Client 룰 기반으로 산정하여 마지막 열(U)에 추가한다.

Usage:
  python generate_transaction_xlsx.py --yyyymm 202504 --company_code ABC --base_dir output
"""
import argparse
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

# OrderMeasure 테이블의 가산/차감 대상 필드 (순서 고정)
MEASURE_FIELDS = [
    "ItemPrice", "ItemTax", "ShippingPrice", "ShippingTax",
    "GiftWrapPrice", "GiftWrapTax", "ItemPromotionDiscount", "ShipPromotionDiscount",
]

# 숫자 타입으로 기록할 시트 열 (B 기준 0-based 인덱스)
# H=6, J=8, K=9, L=10, M=11, O=13, P=14, Q=15, R=16
_NUMERIC_COL_INDICES = {ord(c) - ord('B') for c in "HJKLMNOPQR"}

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

def _calc_performance(order: dict, measure: dict) -> float:
    """OrderMeasure 룰(+/-/NULL)에 따라 트랜잭션별 Performance를 산정한다."""
    total = 0.0
    for field in MEASURE_FIELDS:
        sign = measure.get(field)
        if sign == "+":
            total += float(order.get(field) or 0)
        elif sign == "-":
            total -= float(order.get(field) or 0)
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

    # 고객사 주문 데이터 조회
    orders = _call_sp(
        "SP_Get_AmzOrder_By_Client",
        {"@YYYYMM": args.yyyymm, "@CompanyCode": args.company_code},
    )

    if not orders:
        print(f"WARN: 주문 데이터 없음 ({args.company_code})", file=sys.stderr)

    # OrderMeasure 조회 (Performance 산정 룰: +/-/NULL)
    measures = _call_sp("SP_Get_OrderMeasure_By_Client", {"@CompanyCode": args.company_code})
    measure = measures[0] if measures else {}

    # 고객사 기본 정보
    clients = _call_sp("SP_Get_Client_Info", {"@CompanyCode": args.company_code})
    client = clients[0] if clients else {}

    # 데이터 행 구성 (첫 번째 컬럼 product name 제외, B11부터 기록)
    # H,J,K,L,M,O,P,Q,R 열은 숫자 타입, Performance(U열)는 float으로 마지막에 추가
    data_rows = []
    columns = []
    if orders:
        columns = list(orders[0].keys())[1:]
        for row in orders:
            vals = []
            for i, c in enumerate(columns):
                if i in _NUMERIC_COL_INDICES:
                    vals.append(_to_num(row.get(c)))
                else:
                    vals.append(_safe_str(row.get(c)))
            vals.append(_calc_performance(row, measure))  # Performance (U열, float)
            data_rows.append(vals)

    # Performance 헤더 셀: 데이터 시작 열(B=index 1) + 데이터 컬럼 수
    perf_col = _col_letter(1 + len(columns))
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
        if columns:
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
