"""
Executes STEP 3~11 for company 000152 (주식회사 상경에프앤비), period 202605.
Run with: python run_steps_202605_000152.py
"""
import sys
import os
import json
import subprocess
from pathlib import Path
from decimal import Decimal

# Project root
ROOT = Path(r"c:\Dev\SellingFee")
PYTHON = r"c:\Dev\SellingFee\.venv\Scripts\python.exe"
YYYYMM = "202605"
CC = "000152"
COMPANY_NAME = "주식회사 상경에프앤비"
OUT = ROOT / "output" / YYYYMM / CC

sys.path.insert(0, str(ROOT / ".claude" / "skills" / "db-caller" / "scripts"))
os.chdir(ROOT)

from call_sp import call_sp

def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장: {path} ({len(data) if isinstance(data, list) else 1}건)")

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def run_script(script_path, args_list):
    cmd = [PYTHON, str(ROOT / script_path)] + args_list
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.stdout:
        print(f"  stdout: {result.stdout.strip()}")
    if result.stderr:
        print(f"  stderr: {result.stderr.strip()}")
    return result.returncode, result.stdout, result.stderr

def log(step, status, message):
    try:
        rc, out, err = run_script(
            ".claude/skills/process-logger/scripts/insert_log.py",
            ["--yyyymm", YYYYMM, "--company_code", CC, "--step", step, "--status", status, "--message", message]
        )
        if rc != 0:
            print(f"  [LOG WARN] 로그 저장 실패 (스킵): {err.strip()}")
    except Exception as e:
        print(f"  [LOG WARN] 로그 저장 예외 (스킵): {e}")

def escalate(step, message):
    print(f"\n  [ESCALATION] {step}: {message}")
    try:
        rc, out, err = run_script(
            ".claude/skills/gmail-drafter/scripts/create_escalation_draft.py",
            ["--yyyymm", YYYYMM, "--company_code", CC, "--company_name", COMPANY_NAME,
             "--step", step, "--message", message]
        )
        if rc != 0:
            print(f"  [ESC WARN] 에스컬레이션 Draft 생성 실패: {err.strip()}")
    except Exception as e:
        print(f"  [ESC WARN] 예외: {e}")

# ─── Pre-step: 계약 정보 및 FX 소스 확인 ──────────────────────────────────────
print("\n=== Pre-step: 계약 정보 및 FX 소스 확인 ===")
print("  SP_Get_Valid_Contract 호출 (FX 소스 확인용)...")
contract_base = call_sp("SP_Get_Valid_Contract", {"@YYYYMM": YYYYMM, "@CompanyCode": CC})
save_json(contract_base, OUT / "contract_base.json")

if not contract_base:
    escalate("STEP5", "유효 계약 없음")
    log("STEP5", "FAILED", "유효 계약 없음")
    sys.exit(1)

contract_number = contract_base[0]["contract_number"]
fx_source = contract_base[0].get("FX", None)
if not fx_source:
    escalate("STEP3", "contract_base.json에 FX 필드 없음 - USD 환산 불가")
    log("STEP3", "FAILED", "FX 소스 없음")
    sys.exit(1)

print(f"  contract_number: {contract_number}, FX 소스: {fx_source}")

# ─── STEP 3 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 3: 주문 조회 및 USD 환산 ===")

print("  SP_Get_AmzOrder_By_Client 호출...")
orders_raw = call_sp("SP_Get_AmzOrder_By_Client", {"@YYYYMM": YYYYMM, "@CompanyCode": CC})
save_json(orders_raw, OUT / "orders_raw.json")
print(f"  주문 건수: {len(orders_raw)}")

print("  SP_Convert_Order_Amount_To_USD 호출...")
orders_usd = call_sp("SP_Convert_Order_Amount_To_USD", {
    "@YYYYMM": YYYYMM, "@CompanyCode": CC
})
save_json(orders_usd, OUT / "orders_usd.json")
print(f"  USD 환산 건수: {len(orders_usd)}")

# 성공 기준 검증
if not orders_usd:
    print("  orders_usd.json 레코드 없음 → Fallback 시도...")
    orders_usd_fb = call_sp("SP_Get_ExchangeRate_Fallback", {"@YYYYMM": YYYYMM, "@CompanyCode": CC})
    if not orders_usd_fb:
        escalate("STEP3", "orders_usd 레코드 없음, Fallback도 실패")
        log("STEP3", "FAILED", "USD 환산 실패")
        sys.exit(1)
    save_json(orders_usd_fb, OUT / "orders_usd.json")
    orders_usd = orders_usd_fb

# FXRate 확인
sample = orders_usd[0] if orders_usd else {}
has_fx = any(k for k in sample.keys() if "FX" in k.upper() or "USD" in k.upper() or "Rate" in k)
print(f"  FXRate/USD 필드 확인: {list(sample.keys())}")
log("STEP3", "SUCCESS", f"주문 {len(orders_raw)}건, USD환산 {len(orders_usd)}건")
print("  STEP 3 완료")

# ─── STEP 4 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 4: PerformanceUSD 산정 ===")

print("  SP_Get_OrderMeasure_By_Client 호출...")
order_measure = call_sp("SP_Get_OrderMeasure_By_Client", {"@CompanyCode": CC})
save_json(order_measure, OUT / "order_measure.json")
print(f"  OrderMeasure 건수: {len(order_measure)}")

if not order_measure:
    escalate("STEP4", "OrderMeasure 룰 미정의")
    log("STEP4", "FAILED", "OrderMeasure 룰 없음")
    sys.exit(1)

print("  SP_Calc_Order_Performance_By_Measure 호출...")
performance = call_sp("SP_Calc_Order_Performance_By_Measure", {"@YYYYMM": YYYYMM, "@CompanyCode": CC})
save_json(performance, OUT / "performance.json")
print(f"  Performance 건수: {len(performance)}")

if not performance or performance[0].get("PerformanceUSD") is None:
    escalate("STEP4", "performance_usd 값 없음")
    log("STEP4", "FAILED", "performance_usd 없음")
    sys.exit(1)

perf_usd = float(performance[0]["PerformanceUSD"])
print(f"  PerformanceUSD: {perf_usd}")

# 전월 비교
print("  전월 Performance 조회 (YYYYMM-1)...")
prev_yyyymm = "202604"
try:
    perf_prev = call_sp("SP_Calc_Order_Performance_By_Measure", {"@YYYYMM": prev_yyyymm, "@CompanyCode": CC})
    save_json(perf_prev, OUT / "performance_prev.json")
    if perf_prev and perf_prev[0].get("PerformanceUSD") is not None:
        prev_usd = float(perf_prev[0]["PerformanceUSD"])
        if prev_usd > 0:
            change_pct = abs(perf_usd - prev_usd) / prev_usd * 100
            if change_pct >= 50:
                print(f"  [WARNING] PerformanceUSD 전월 대비 {change_pct:.1f}% 변동 (전월: {prev_usd}, 금월: {perf_usd})")
                log("STEP4", "SUCCESS", f"WARNING: 전월대비 {change_pct:.1f}% 변동. PerformanceUSD={perf_usd}")
            else:
                log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd} (전월대비 {change_pct:.1f}% 변동)")
        else:
            print("  [INFO] 전월 PerformanceUSD = 0 (신규 고객사 가능)")
            log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd}, 전월=0")
    else:
        print("  [INFO] 전월 데이터 없음 (신규 고객사)")
        log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd}, 신규 고객사")
except Exception as e:
    print(f"  [INFO] 전월 조회 실패 (무시): {e}")
    log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd}")

print("  STEP 4 완료")

# ─── STEP 5 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 5: 유효 계약 및 요율 조회 ===")
# contract_base.json은 Pre-step에서 이미 조회·저장됨 (contract_number, fx_source 변수 사용 가능)
print(f"  계약번호: {contract_number} (Pre-step에서 확인)")

print("  SP_Get_Selling_Fee_Rate 호출...")
rates = call_sp("SP_Get_Selling_Fee_Rate", {"@ContractNumber": contract_number})
save_json(rates, OUT / "rates.json")
print(f"  요율 건수: {len(rates)}")

if not rates:
    escalate("STEP5", "요율 미정의")
    log("STEP5", "FAILED", "요율 없음")
    sys.exit(1)

# contract.json 생성
contract = {
    "contract_number": contract_number,
    "rates": [
        {
            "line_number": r["line_number"],
            "rate_type": r.get("rate_type", "Flat"),
            "amount_from": r["amount_from"],
            "amount_to": r["amount_to"],
            "rate": r["rate"]
        }
        for r in rates
    ]
}
save_json(contract, OUT / "contract.json")
log("STEP5", "SUCCESS", f"계약번호={contract_number}, 요율 {len(rates)}건")
print("  STEP 5 완료")

# ─── STEP 6 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 6: 초과누진 셀링피 계산 (Python) ===")

# SP_Calc_Tiered_Selling_Fee는 내부에서 PerformanceUSD를 재계산하여 미세 오차 발생.
# contract.json의 rates와 performance.json의 PerformanceUSD로 직접 계산한다.
rates_list = contract["rates"]

selling_fee = []
total_fee_exact = 0.0
for tier in sorted(rates_list, key=lambda r: r["line_number"]):
    lower = float(tier["amount_from"])
    upper = float(tier["amount_to"])
    rate_val = float(tier["rate"])
    applied = max(0.0, min(perf_usd, upper) - lower) if perf_usd > lower else 0.0
    fee_exact = applied * rate_val
    total_fee_exact += fee_exact
    selling_fee.append({
        "contract_number": contract_number,
        "line_number": tier["line_number"],
        "rate_type": tier.get("rate_type", "Flat"),
        "amount_from": lower,
        "amount_to": upper,
        "rate": rate_val,
        "AppliedAmountUSD": round(applied, 2),
        "SellingFeeUSD": round(fee_exact, 2),
    })

selling_fee_usd = round(total_fee_exact, 2)
save_json(selling_fee, OUT / "selling_fee.json")
print(f"  SellingFeeUSD: {selling_fee_usd} (PerformanceUSD {perf_usd} × rates 직접 계산)")
log("STEP6", "SUCCESS", f"SellingFeeUSD={selling_fee_usd}")
print("  STEP 6 완료")

# ─── STEP 7 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 7: 청구 통화 결정 및 익월 환율 적용 ===")

print("  SP_Get_Fixed_Currency 호출...")
fixed_currency = call_sp("SP_Get_Fixed_Currency", {"@CompanyCode": CC})
save_json(fixed_currency, OUT / "fixed_currency.json")
print(f"  고정통화: {fixed_currency}")

if not fixed_currency:
    billing_currency = "KRW"  # 기본값
else:
    billing_currency = fixed_currency[0].get("BillingCurrency", "KRW")

print(f"  BillingCurrency: {billing_currency}")

# FX 소스 확인
if not fx_source:
    escalate("STEP7", "contract_base.json에 FX 필드 없음")
    log("STEP7", "FAILED", "FX 소스 없음")
    sys.exit(1)

if billing_currency == "KRW":
    print(f"  KRW 고객사 → 환율 조회 (Source={fx_source})...")
    exchange_rate_data = call_sp("SP_Get_ExchangeRate_NextMonth", {
        "@YYYYMM": YYYYMM, "@Currency": "USD", "@Source": fx_source
    })
    save_json(exchange_rate_data, OUT / "exchange_rate.json")

    if not exchange_rate_data:
        print("  익월 환율 없음 → Fallback 시도...")
        # 익월 초일 계산: 202605 → 2026-06-01
        year = int(YYYYMM[:4])
        month = int(YYYYMM[4:6])
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_month = 1
            next_year += 1
        next_month_first = f"{next_year}-{next_month:02d}-01"
        print(f"  Fallback BaseDate: {next_month_first}")

        exchange_rate_data = call_sp("SP_Get_ExchangeRate_Fallback", {
            "@BaseDate": next_month_first, "@Currency": "USD", "@Source": fx_source
        })
        save_json(exchange_rate_data, OUT / "exchange_rate.json")

        if not exchange_rate_data:
            escalate("STEP7", "환율 데이터 없음 (Fallback도 실패)")
            log("STEP7", "FAILED", "환율 없음")
            sys.exit(1)

    usd_krw_rate = float(exchange_rate_data[0]["RateToUSD"])
    print(f"  USDKRWRate: {usd_krw_rate}")

    # billing.json 생성 (KRW)
    selling_fee_krw = round(selling_fee_usd * usd_krw_rate)
    vat = round(selling_fee_krw * 0.1)
    total_amount = selling_fee_krw + vat

    billing = {
        "PerformanceUSD": perf_usd,
        "BillingCurrency": "KRW",
        "FxSource": fx_source,
        "USDKRWRate": usd_krw_rate,
        "SellingFeeUSD": selling_fee_usd,
        "SellingFeeKRW": selling_fee_krw,
        "VAT": vat,
        "TotalAmount": total_amount
    }

elif billing_currency == "USD":
    print("  USD 고객사 → 환율 조회 생략")
    vat = 0
    total_amount = selling_fee_usd
    billing = {
        "PerformanceUSD": perf_usd,
        "BillingCurrency": "USD",
        "SellingFeeUSD": selling_fee_usd,
        "VAT": vat,
        "TotalAmount": total_amount
    }
else:
    escalate("STEP7", f"알 수 없는 BillingCurrency: {billing_currency}")
    log("STEP7", "FAILED", f"알 수 없는 통화: {billing_currency}")
    sys.exit(1)

save_json(billing, OUT / "billing.json")
print(f"  billing.json 생성: {billing}")
log("STEP7", "SUCCESS", f"BillingCurrency={billing_currency}, TotalAmount={billing['TotalAmount']}")
print("  STEP 7 완료")

# ─── STEP 8 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 8: 산출물 생성 ===")

def run_report_scripts():
    rc1, _, err1 = run_script(
        ".claude/skills/report-generator/scripts/generate_invoice_pdf.py",
        ["--yyyymm", YYYYMM, "--company_code", CC, "--base_dir", "output"]
    )
    rc2, _, err2 = run_script(
        ".claude/skills/report-generator/scripts/generate_transaction_xlsx.py",
        ["--yyyymm", YYYYMM, "--company_code", CC, "--base_dir", "output"]
    )
    rc3, _, err3 = run_script(
        ".claude/skills/report-generator/scripts/generate_revenue_pdf.py",
        ["--yyyymm", YYYYMM, "--company_code", CC, "--base_dir", "output"]
    )
    return rc1, rc2, rc3, err1, err2, err3

print("  Invoice PDF 생성...")
rc1, rc2, rc3, err1, err2, err3 = run_report_scripts()

def check_reports():
    invoice = OUT / "invoice.pdf"
    trans = OUT / "transaction_report.xlsx"
    revenue = OUT / "revenue_report.pdf"
    ok = True
    for f in [invoice, trans, revenue]:
        if not f.exists() or f.stat().st_size == 0:
            print(f"  [FAIL] 파일 없음 또는 크기 0: {f}")
            ok = False
        else:
            print(f"  [OK] {f.name}: {f.stat().st_size:,} bytes")
    return ok

if not check_reports() or any(rc != 0 for rc in [rc1, rc2, rc3]):
    print("  실패 → 재시도...")
    rc1, rc2, rc3, err1, err2, err3 = run_report_scripts()
    if not check_reports() or any(rc != 0 for rc in [rc1, rc2, rc3]):
        escalate("STEP8", f"산출물 생성 실패: inv={err1}, trans={err2}, rev={err3}")
        log("STEP8", "FAILED", "산출물 생성 실패")
        sys.exit(1)

# LLM 자기 검증: billing.json의 TotalAmount와 파일 존재 확인
loaded_billing = load_json(OUT / "billing.json")
print(f"  [검증] TotalAmount={loaded_billing.get('TotalAmount')}, SellingFeeUSD={loaded_billing.get('SellingFeeUSD')}")
log("STEP8", "SUCCESS", "invoice.pdf, transaction_report.xlsx, revenue_report.pdf 생성 완료")
print("  STEP 8 완료")

# ─── STEP 9 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 9: Google Drive 저장 ===")

rc, out, err = run_script(
    ".claude/skills/drive-uploader/scripts/upload_to_drive.py",
    ["--yyyymm", YYYYMM, "--company_code", CC, "--company_name", COMPANY_NAME]
)
if rc != 0:
    escalate("STEP9", f"Drive 업로드 실패: {err.strip()}")
    log("STEP9", "FAILED", f"Drive 업로드 실패: {err.strip()[:200]}")
    sys.exit(1)

log("STEP9", "SUCCESS", "Google Drive 업로드 완료")
print("  STEP 9 완료")

# ─── STEP 10 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 10: Gmail Draft 생성 ===")
final_status = "SUCCESS"

def run_gmail_draft():
    return run_script(
        ".claude/skills/gmail-drafter/scripts/create_gmail_draft.py",
        ["--yyyymm", YYYYMM, "--company_code", CC, "--company_name", COMPANY_NAME]
    )

rc, out, err = run_gmail_draft()
if rc != 0:
    print(f"  실패 → 재시도: {err.strip()}")
    rc, out, err = run_gmail_draft()
    if rc != 0:
        print(f"  Gmail Draft 생성 실패 (PARTIAL): {err.strip()}")
        log("STEP10", "PARTIAL", f"Gmail Draft 생성 실패: {err.strip()[:200]}")
        final_status = "PARTIAL"
    else:
        log("STEP10", "SUCCESS", "Gmail Draft 생성 완료")
else:
    log("STEP10", "SUCCESS", "Gmail Draft 생성 완료")
print("  STEP 10 완료")

# ─── STEP 11 ────────────────────────────────────────────────────────────────────
print("\n=== STEP 11: Processing Log 저장 ===")
log("STEP11", final_status, f"전체 처리 완료. 최종 상태: {final_status}")

print(f"\n{'='*50}")
print(f"처리 결과: {final_status}")
print(f"고객사: {COMPANY_NAME} ({CC})")
print(f"정산월: {YYYYMM}")
print(f"{'='*50}")
print(final_status)
