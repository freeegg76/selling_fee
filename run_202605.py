"""
202605 정산 전체 실행 스크립트.
Run with: python run_202605.py
"""
import sys
import os
import json
import subprocess
from pathlib import Path

ROOT = Path(r"c:\Dev\SellingFee")
PYTHON = r"c:\Dev\SellingFee\.venv\Scripts\python.exe"
YYYYMM = "202605"
OUT_BASE = ROOT / "output" / YYYYMM

sys.path.insert(0, str(ROOT / ".claude" / "skills" / "db-caller" / "scripts"))
os.chdir(ROOT)

from call_sp import call_sp


def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(data) if isinstance(data, list) else 1
    print(f"  저장: {path.relative_to(ROOT)} ({n}건)")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_script(script_path, args_list):
    cmd = [PYTHON, str(ROOT / script_path)] + args_list
    result = subprocess.run(cmd, capture_output=True, cwd=str(ROOT))
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if stdout:
        print(f"    stdout: {stdout.strip()}")
    if stderr:
        print(f"    stderr: {stderr.strip()}")
    return result.returncode, stdout, stderr


def run_client(company_code: str, company_name: str):
    OUT = OUT_BASE / company_code
    print(f"\n{'='*60}")
    print(f"처리 시작: {company_name} ({company_code})")
    print(f"{'='*60}")

    def log(step, status, message):
        try:
            run_script(".claude/skills/process-logger/scripts/insert_log.py",
                       ["--yyyymm", YYYYMM, "--company_code", company_code,
                        "--step", step, "--status", status, "--message", message])
        except Exception as e:
            print(f"  [LOG WARN] {e}")

    def escalate(step, message):
        print(f"  [ESCALATION] {step}: {message}")
        try:
            run_script(".claude/skills/gmail-drafter/scripts/create_escalation_draft.py",
                       ["--yyyymm", YYYYMM, "--company_code", company_code,
                        "--company_name", company_name, "--step", step, "--message", message])
        except Exception as e:
            print(f"  [ESC WARN] {e}")

    # ── Pre-step: 계약 정보 및 FX 소스 확인 ──────────────────────────────────
    print("\n  [Pre-step] 계약 정보 및 FX 소스 확인")
    contract_base = call_sp("SP_Get_Valid_Contract", {"@YYYYMM": YYYYMM, "@CompanyCode": company_code})
    save_json(contract_base, OUT / "contract_base.json")

    if not contract_base:
        escalate("STEP5", "유효 계약 없음")
        log("STEP5", "FAILED", "유효 계약 없음")
        return f"FAILED: {company_name} - STEP5 - 유효 계약 없음"

    contract_number = contract_base[0]["contract_number"]
    fx_source = contract_base[0].get("FX", None)
    if not fx_source:
        escalate("STEP3", "FX 필드 없음 - USD 환산 불가")
        log("STEP3", "FAILED", "FX 소스 없음")
        return f"FAILED: {company_name} - STEP3 - FX 소스 없음"

    print(f"  contract_number={contract_number}, FX={fx_source}")

    # ── STEP 3: 주문 조회 및 USD 환산 ────────────────────────────────────────
    print("\n  [STEP 3] 주문 조회 및 USD 환산")
    orders_raw = call_sp("SP_Get_AmzOrder_By_Client", {"@YYYYMM": YYYYMM, "@CompanyCode": company_code})
    save_json(orders_raw, OUT / "orders_raw.json")
    print(f"  주문 건수: {len(orders_raw)}")

    orders_usd = call_sp("SP_Convert_Order_Amount_To_USD", {
        "@YYYYMM": YYYYMM, "@CompanyCode": company_code
    })
    save_json(orders_usd, OUT / "orders_usd.json")
    print(f"  USD 환산 건수: {len(orders_usd)}")

    if not orders_usd:
        print("  orders_usd 없음 → Fallback 시도...")
        year = int(YYYYMM[:4])
        month = int(YYYYMM[4:6])
        next_m = month % 12 + 1
        next_y = year + (1 if month == 12 else 0)
        fallback = call_sp("SP_Get_ExchangeRate_Fallback", {
            "@BaseDate": f"{next_y}-{next_m:02d}-01", "@Currency": "USD", "@Source": fx_source
        })
        if not fallback:
            escalate("STEP3", "orders_usd 없음, Fallback도 실패")
            log("STEP3", "FAILED", "USD 환산 실패")
            return f"FAILED: {company_name} - STEP3 - USD 환산 실패"
        save_json(fallback, OUT / "orders_usd.json")
        orders_usd = fallback

    log("STEP3", "SUCCESS", f"주문 {len(orders_raw)}건, USD환산 {len(orders_usd)}건")

    # ── STEP 4: PerformanceUSD 산정 ──────────────────────────────────────────
    print("\n  [STEP 4] PerformanceUSD 산정")
    order_measure = call_sp("SP_Get_OrderMeasure_By_Client", {"@CompanyCode": company_code})
    save_json(order_measure, OUT / "order_measure.json")

    if not order_measure:
        escalate("STEP4", "OrderMeasure 룰 미정의")
        log("STEP4", "FAILED", "OrderMeasure 없음")
        return f"FAILED: {company_name} - STEP4 - OrderMeasure 없음"

    performance = call_sp("SP_Calc_Order_Performance_By_Measure", {"@YYYYMM": YYYYMM, "@CompanyCode": company_code})
    save_json(performance, OUT / "performance.json")

    if not performance or performance[0].get("PerformanceUSD") is None:
        escalate("STEP4", "performance_usd 값 없음")
        log("STEP4", "FAILED", "PerformanceUSD 없음")
        return f"FAILED: {company_name} - STEP4 - PerformanceUSD 없음"

    perf_usd = float(performance[0]["PerformanceUSD"])
    print(f"  PerformanceUSD: {perf_usd}")

    # 전월 비교
    prev_yyyymm = "202604"
    try:
        perf_prev = call_sp("SP_Calc_Order_Performance_By_Measure", {"@YYYYMM": prev_yyyymm, "@CompanyCode": company_code})
        save_json(perf_prev, OUT / "performance_prev.json")
        if perf_prev and perf_prev[0].get("PerformanceUSD") and float(perf_prev[0]["PerformanceUSD"]) > 0:
            prev_usd = float(perf_prev[0]["PerformanceUSD"])
            change_pct = abs(perf_usd - prev_usd) / prev_usd * 100
            if change_pct >= 50:
                print(f"  [WARNING] 전월 대비 {change_pct:.1f}% 변동 (전월: {prev_usd})")
                log("STEP4", "SUCCESS", f"WARNING: 전월대비 {change_pct:.1f}% 변동. PerformanceUSD={perf_usd}")
            else:
                log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd}")
        else:
            log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd} (신규 또는 전월 없음)")
    except Exception as e:
        print(f"  [INFO] 전월 조회 실패 (무시): {e}")
        log("STEP4", "SUCCESS", f"PerformanceUSD={perf_usd}")

    # ── STEP 5: 요율 조회 ────────────────────────────────────────────────────
    print("\n  [STEP 5] 요율 조회")
    rates = call_sp("SP_Get_Selling_Fee_Rate", {"@ContractNumber": contract_number})
    save_json(rates, OUT / "rates.json")
    print(f"  요율 건수: {len(rates)}")

    if not rates:
        escalate("STEP5", "요율 미정의")
        log("STEP5", "FAILED", "요율 없음")
        return f"FAILED: {company_name} - STEP5 - 요율 없음"

    contract = {
        "contract_number": contract_number,
        "rates": [
            {"line_number": r["line_number"], "rate_type": r.get("rate_type", "Flat"),
             "amount_from": r["amount_from"], "amount_to": r["amount_to"], "rate": r["rate"]}
            for r in rates
        ]
    }
    save_json(contract, OUT / "contract.json")
    log("STEP5", "SUCCESS", f"계약번호={contract_number}, 요율 {len(rates)}건")

    # ── STEP 6: 셀링피 계산 (Python 직접) ────────────────────────────────────
    print("\n  [STEP 6] 셀링피 계산 (Python)")
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
            "amount_from": lower, "amount_to": upper, "rate": rate_val,
            "AppliedAmountUSD": round(applied, 2),
            "SellingFeeUSD": round(fee_exact, 2),
        })
    selling_fee_usd = round(total_fee_exact, 2)
    save_json(selling_fee, OUT / "selling_fee.json")
    print(f"  SellingFeeUSD: {selling_fee_usd}")
    log("STEP6", "SUCCESS", f"SellingFeeUSD={selling_fee_usd}")

    # ── STEP 7: 청구 통화 및 환율 ─────────────────────────────────────────────
    print("\n  [STEP 7] 청구 통화 및 환율 적용")
    fixed_currency = call_sp("SP_Get_Fixed_Currency", {"@CompanyCode": company_code})
    save_json(fixed_currency, OUT / "fixed_currency.json")
    billing_currency = fixed_currency[0].get("BillingCurrency", "KRW") if fixed_currency else "KRW"
    print(f"  BillingCurrency: {billing_currency}")

    if billing_currency == "KRW":
        exchange_rate_data = call_sp("SP_Get_ExchangeRate_NextMonth", {
            "@YYYYMM": YYYYMM, "@Currency": "USD", "@Source": fx_source
        })
        save_json(exchange_rate_data, OUT / "exchange_rate.json")

        if not exchange_rate_data:
            print("  익월 환율 없음 → Fallback 시도...")
            year, month = int(YYYYMM[:4]), int(YYYYMM[4:6])
            next_m = month % 12 + 1
            next_y = year + (1 if month == 12 else 0)
            exchange_rate_data = call_sp("SP_Get_ExchangeRate_Fallback", {
                "@BaseDate": f"{next_y}-{next_m:02d}-01", "@Currency": "USD", "@Source": fx_source
            })
            save_json(exchange_rate_data, OUT / "exchange_rate.json")

        if not exchange_rate_data:
            escalate("STEP7", "환율 데이터 없음 (Fallback 포함)")
            log("STEP7", "FAILED", "환율 없음")
            return f"FAILED: {company_name} - STEP7 - 환율 없음"

        usd_krw_rate = float(exchange_rate_data[0]["RateToUSD"])
        selling_fee_krw = round(selling_fee_usd * usd_krw_rate)
        vat = round(selling_fee_krw * 0.1)
        total_amount = selling_fee_krw + vat
        billing = {
            "PerformanceUSD": perf_usd, "BillingCurrency": "KRW",
            "FxSource": fx_source, "USDKRWRate": usd_krw_rate,
            "SellingFeeUSD": selling_fee_usd, "SellingFeeKRW": selling_fee_krw,
            "VAT": vat, "TotalAmount": total_amount
        }
        print(f"  USDKRWRate={usd_krw_rate}, SellingFeeKRW={selling_fee_krw}, VAT={vat}, Total={total_amount}")

    elif billing_currency == "USD":
        billing = {
            "PerformanceUSD": perf_usd, "BillingCurrency": "USD",
            "SellingFeeUSD": selling_fee_usd, "VAT": 0, "TotalAmount": selling_fee_usd
        }
        print(f"  USD 고객사 → TotalAmount={selling_fee_usd}")

    else:
        escalate("STEP7", f"알 수 없는 BillingCurrency: {billing_currency}")
        log("STEP7", "FAILED", f"알 수 없는 통화: {billing_currency}")
        return f"FAILED: {company_name} - STEP7 - 알 수 없는 통화"

    save_json(billing, OUT / "billing.json")
    log("STEP7", "SUCCESS", f"BillingCurrency={billing_currency}, TotalAmount={billing['TotalAmount']}")

    # ── STEP 8: 산출물 생성 ──────────────────────────────────────────────────
    print("\n  [STEP 8] 산출물 생성")

    def run_reports():
        r1, _, e1 = run_script(".claude/skills/report-generator/scripts/generate_invoice_pdf.py",
                               ["--yyyymm", YYYYMM, "--company_code", company_code, "--base_dir", "output"])
        r2, _, e2 = run_script(".claude/skills/report-generator/scripts/generate_transaction_xlsx.py",
                               ["--yyyymm", YYYYMM, "--company_code", company_code, "--base_dir", "output"])
        r3, _, e3 = run_script(".claude/skills/report-generator/scripts/generate_revenue_pdf.py",
                               ["--yyyymm", YYYYMM, "--company_code", company_code, "--base_dir", "output"])
        return r1, r2, r3, e1, e2, e3

    def check_reports():
        ok = True
        for fname in ["invoice.pdf", "transaction_report.xlsx", "revenue_report.pdf"]:
            f = OUT / fname
            if not f.exists() or f.stat().st_size == 0:
                print(f"  [FAIL] {fname} 없음 또는 크기 0")
                ok = False
            else:
                print(f"  [OK] {fname}: {f.stat().st_size:,} bytes")
        return ok

    rc1, rc2, rc3, e1, e2, e3 = run_reports()
    if not check_reports() or any(rc != 0 for rc in [rc1, rc2, rc3]):
        print("  실패 → 재시도...")
        rc1, rc2, rc3, e1, e2, e3 = run_reports()
        if not check_reports() or any(rc != 0 for rc in [rc1, rc2, rc3]):
            escalate("STEP8", f"산출물 생성 실패: inv={e1[:100]}, trans={e2[:100]}, rev={e3[:100]}")
            log("STEP8", "FAILED", "산출물 생성 실패")
            return f"FAILED: {company_name} - STEP8 - 산출물 생성 실패"

    log("STEP8", "SUCCESS", "invoice.pdf, transaction_report.xlsx, revenue_report.pdf 생성 완료")

    # ── STEP 9: Google Drive 저장 ────────────────────────────────────────────
    print("\n  [STEP 9] Google Drive 저장")
    rc, _, err = run_script(".claude/skills/drive-uploader/scripts/upload_to_drive.py",
                            ["--yyyymm", YYYYMM, "--company_code", company_code, "--company_name", company_name])
    if rc != 0:
        escalate("STEP9", f"Drive 업로드 실패: {err.strip()[:200]}")
        log("STEP9", "FAILED", f"Drive 업로드 실패")
        return f"FAILED: {company_name} - STEP9 - Drive 업로드 실패"
    log("STEP9", "SUCCESS", "Google Drive 업로드 완료")

    # ── STEP 10: Gmail Draft ─────────────────────────────────────────────────
    print("\n  [STEP 10] Gmail Draft 생성")
    final_status = "SUCCESS"
    rc, _, err = run_script(".claude/skills/gmail-drafter/scripts/create_gmail_draft.py",
                            ["--yyyymm", YYYYMM, "--company_code", company_code, "--company_name", company_name])
    if rc != 0:
        print(f"  실패 → 재시도...")
        rc, _, err = run_script(".claude/skills/gmail-drafter/scripts/create_gmail_draft.py",
                                ["--yyyymm", YYYYMM, "--company_code", company_code, "--company_name", company_name])
        if rc != 0:
            print(f"  Gmail Draft 실패 (PARTIAL): {err.strip()[:200]}")
            log("STEP10", "PARTIAL", f"Gmail Draft 실패: {err.strip()[:200]}")
            final_status = "PARTIAL"
        else:
            log("STEP10", "SUCCESS", "Gmail Draft 생성 완료")
    else:
        log("STEP10", "SUCCESS", "Gmail Draft 생성 완료")

    # ── STEP 11 ──────────────────────────────────────────────────────────────
    log("STEP11", final_status, f"전체 처리 완료. 최종 상태: {final_status}")
    print(f"\n  → {company_name} ({company_code}): {final_status}")
    return final_status


# ── STEP 1: 처리 대상 고객사 조회 ─────────────────────────────────────────────
print("\n=== STEP 1: 처리 대상 고객사 조회 ===")
clients_raw = call_sp("SP_Get_AmzOrder_By_Period", {"@YYYYMM": YYYYMM})
save_json(clients_raw, OUT_BASE / "clients_raw.json")
print(f"  전체 주문 건수: {len(clients_raw)}")

if not clients_raw:
    print("ERROR: 주문 데이터 없음. 에스컬레이션 필요.")
    sys.exit(1)

# 고유 고객사 추출 (SP 결과의 'Client' 컬럼 = company_code)
seen_codes = set()
client_codes = []
for row in clients_raw:
    code = row.get("company_code") or row.get("Client")
    if code and code not in seen_codes:
        seen_codes.add(code)
        client_codes.append(code)

# 각 고객사 이름 조회
clients = []
for code in client_codes:
    info = call_sp("SP_Get_Client_Info", {"@CompanyCode": code})
    name = info[0].get("company_name", code) if info else code
    clients.append({"company_code": code, "company_name": name})

save_json(clients, OUT_BASE / "clients.json")
print(f"  고객사 수: {len(clients)}")
for c in clients:
    print(f"    - {c['company_code']}: {c['company_name']}")

# ── STEP 2: 고객사별 순차 처리 ────────────────────────────────────────────────
print(f"\n=== STEP 2~11: {len(clients)}개 고객사 처리 시작 ===")

results = {}
for c in clients:
    try:
        result = run_client(c["company_code"], c["company_name"])
        results[c["company_code"]] = {"name": c["company_name"], "status": result}
    except Exception as e:
        results[c["company_code"]] = {"name": c["company_name"], "status": f"FAILED: {e}"}
        print(f"\n  [EXCEPTION] {c['company_name']}: {e}")

# ── STEP 12: 전체 결과 집계 ───────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"=== 판매수수료 정산 완료 ({YYYYMM}) ===")
print(f"{'='*60}")

success = [k for k, v in results.items() if v["status"] == "SUCCESS"]
partial = [k for k, v in results.items() if isinstance(v["status"], str) and "PARTIAL" in v["status"]]
failed  = [k for k, v in results.items() if isinstance(v["status"], str) and "FAILED" in v["status"]]

print(f"SUCCESS : {len(success)}개사")
print(f"PARTIAL : {len(partial)}개사" + (f" → {[results[k]['name'] for k in partial]}" if partial else ""))
print(f"FAILED  : {len(failed)}개사" + (f" → {[results[k]['name'] for k in failed]}" if failed else ""))
