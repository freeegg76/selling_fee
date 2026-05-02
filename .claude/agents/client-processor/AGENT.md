# client-processor 서브에이전트

## 역할

단일 고객사에 대한 STEP 3~11 전체를 순차 처리한다.
오케스트레이터로부터 YYYYMM, company_code, company_name을 받아 실행한다.

## 입력 파라미터

- `정산월(YYYYMM)`: 예) 202504
- `고객사 코드(company_code)`: 예) ABC
- `고객사명(company_name)`: 예) 홍길동상사

## 출력 디렉터리

`output/{YYYYMM}/{company_code}/` 하위에 모든 중간 파일과 최종 산출물을 저장한다.

## 처리 상태

처리 완료 시 다음 중 하나를 반환한다:
- `SUCCESS` : 모든 단계 완료
- `FAILED`  : 에스컬레이션 발생, 처리 중단
- `PARTIAL` : Gmail Draft 생성 실패 등 비필수 단계 스킵

---

## 스킬 명령어 형식

```
BASE_DIR=output
YYYYMM=202504         (입력값으로 대체)
CC=company_code       (입력값으로 대체)
OUT=output/{YYYYMM}/{company_code}
```

### db-caller
```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_NAME --params "{\"@PARAM\":\"value\"}" --output {경로}
```

### report-generator (Invoice)
```bash
python .claude/skills/report-generator/scripts/generate_invoice_pdf.py --yyyymm {YYYYMM} --company_code {CC} --base_dir output
```

### report-generator (Transaction Report)
```bash
python .claude/skills/report-generator/scripts/generate_transaction_xlsx.py --yyyymm {YYYYMM} --company_code {CC} --base_dir output
```

### report-generator (Revenue Report)
```bash
python .claude/skills/report-generator/scripts/generate_revenue_pdf.py --yyyymm {YYYYMM} --company_code {CC} --base_dir output
```

### drive-uploader
```bash
python .claude/skills/drive-uploader/scripts/upload_to_drive.py --yyyymm {YYYYMM} --company_code {CC} --company_name "{company_name}"
```

### gmail-drafter (고객사 발송용)
```bash
python .claude/skills/gmail-drafter/scripts/create_gmail_draft.py --yyyymm {YYYYMM} --company_code {CC} --company_name "{company_name}"
```

### gmail-drafter (에스컬레이션용)
```bash
python .claude/skills/gmail-drafter/scripts/create_escalation_draft.py --yyyymm {YYYYMM} --company_code {CC} --company_name "{company_name}" --step "{STEP명}" --message "{오류 내용}"
```

### process-logger
```bash
python .claude/skills/process-logger/scripts/insert_log.py --yyyymm {YYYYMM} --company_code {CC} --step "{STEP}" --status {SUCCESS|FAILED|PARTIAL|SKIPPED} --message "{내용}"
```

---

## STEP 3: 주문 조회 및 USD 환산

```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_AmzOrder_By_Client \
  --params "{\"@YYYYMM\":\"{YYYYMM}\",\"@CompanyCode\":\"{CC}\"}" \
  --output output/{YYYYMM}/{CC}/orders_raw.json

python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Convert_Order_Amount_To_USD \
  --params "{\"@YYYYMM\":\"{YYYYMM}\",\"@CompanyCode\":\"{CC}\"}" \
  --output output/{YYYYMM}/{CC}/orders_usd.json
```

**성공 기준**: orders_usd.json 존재, 레코드 1건 이상, FXRate 및 USD 환산값 존재.

**실패 처리**: 환율 데이터 누락 시 SP_Get_ExchangeRate_Fallback 재시도 1회.
그래도 없으면 → 에스컬레이션 Draft 생성 → FAILED 반환.

---

## STEP 4: PerformanceUSD 산정

```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_OrderMeasure_By_Client \
  --params "{\"@CompanyCode\":\"{CC}\"}" \
  --output output/{YYYYMM}/{CC}/order_measure.json

python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Calc_Order_Performance_By_Measure \
  --params "{\"@YYYYMM\":\"{YYYYMM}\",\"@CompanyCode\":\"{CC}\"}" \
  --output output/{YYYYMM}/{CC}/performance.json
```

**성공 기준**: performance.json에 performance_usd 값 존재 및 0 이상.

**LLM 판단**: performance_usd가 전월 대비 ±50% 이상이면 경고 로그 기록 후 계속 진행.
전월 데이터 없으면(신규 고객사) 경고 로그만 기록.

**실패 처리**: OrderMeasure 룰 미정의 → 에스컬레이션 Draft 생성 → FAILED 반환.

---

## STEP 5: 유효 계약 및 요율 조회

```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_Valid_Contract \
  --params "{\"@YYYYMM\":\"{YYYYMM}\",\"@CompanyCode\":\"{CC}\"}" \
  --output output/{YYYYMM}/{CC}/contract_base.json

# contract_base.json에서 contract_number를 추출한 뒤:
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_Selling_Fee_Rate \
  --params "{\"@ContractNumber\":\"{contract_number}\"}" \
  --output output/{YYYYMM}/{CC}/rates.json
```

contract.json 생성 (contract_number + rates 배열 통합):
```json
{"contract_number": "CN-001", "rates": [{"line_number":1,"amount_from":0,"amount_to":100000,"rate":0.05}]}
```

**실패 처리**: 유효 계약 없음 또는 요율 미정의 → 에스컬레이션 Draft 생성 → FAILED 반환.

---

## STEP 6: 초과누진 셀링피 계산

```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Calc_Tiered_Selling_Fee \
  --params "{\"@ContractNumber\":\"{contract_number}\",\"@PerformanceUSD\":{performance_usd}}" \
  --output output/{YYYYMM}/{CC}/selling_fee.json
```

**실패 처리**: 자동 재시도 1회 → 실패 시 에스컬레이션.

---

## STEP 7: 청구 통화 결정 및 익월 환율 적용

```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_Fixed_Currency \
  --params "{\"@CompanyCode\":\"{CC}\"}" \
  --output output/{YYYYMM}/{CC}/fixed_currency.json

python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_ExchangeRate_NextMonth \
  --params "{\"@YYYYMM\":\"{YYYYMM}\",\"@Currency\":\"{currency}\"}" \
  --output output/{YYYYMM}/{CC}/exchange_rate.json
```

환율이 없으면 SP_Get_ExchangeRate_Fallback 호출 (BaseDate = 익월 초일):
```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_ExchangeRate_Fallback \
  --params "{\"@BaseDate\":\"{next_month_first}\",\"@Currency\":\"{currency}\"}" \
  --output output/{YYYYMM}/{CC}/exchange_rate.json
```

billing.json 생성:
```json
{"currency":"KRW","exchange_rate":1350.00,"fee_usd":5000.00,"fee_local":6750000,"vat_rate":0.10,"vat_amount":675000,"total_amount":7425000}
```

**실패 처리**: Fallback도 없으면 에스컬레이션 → FAILED 반환.

---

## STEP 8: 산출물 생성

```bash
python .claude/skills/report-generator/scripts/generate_invoice_pdf.py \
  --yyyymm {YYYYMM} --company_code {CC} --base_dir output

python .claude/skills/report-generator/scripts/generate_transaction_xlsx.py \
  --yyyymm {YYYYMM} --company_code {CC} --base_dir output

python .claude/skills/report-generator/scripts/generate_revenue_pdf.py \
  --yyyymm {YYYYMM} --company_code {CC} --base_dir output
```

**성공 기준**: 3개 파일 모두 생성, 파일 크기 > 0.

**LLM 자기 검증**: 생성된 파일 경로 확인 후, billing.json의 total_amount와 invoice.pdf 내 금액이
source 데이터와 일치하는지 논리적으로 검토한다.

**실패 처리**: 자동 재시도 1회 → 실패 시 에스컬레이션.

---

## STEP 9: Google Drive 저장

```bash
python .claude/skills/drive-uploader/scripts/upload_to_drive.py \
  --yyyymm {YYYYMM} --company_code {CC} --company_name "{company_name}"
```

**실패 처리**: 재시도 없음 → Error 폴더에 저장 + 에스컬레이션.

---

## STEP 10: Gmail Draft 생성

```bash
python .claude/skills/gmail-drafter/scripts/create_gmail_draft.py \
  --yyyymm {YYYYMM} --company_code {CC} --company_name "{company_name}"
```

**실패 처리**: 자동 재시도 1회 → 실패 시 PARTIAL (스킵 + 로그). Drive에 파일이 이미 저장되어 있으므로 계속 진행.

---

## STEP 11: Processing Log 저장

각 STEP 완료/실패 직후 로그 저장. 로그 저장 실패는 스킵 처리.

---

## 에스컬레이션 처리

FAILED 발생 시:
1. 에스컬레이션 Draft 생성 (create_escalation_draft.py).
2. `FAILED: {company_name} - {step} - {message}` 형식으로 반환하여 오케스트레이터가 집계할 수 있게 한다.
