# 판매수수료 자동화 에이전트 시스템 설계서

> **문서 목적**: Claude Code 구현 시 참조할 계획서
> **작성 기준일**: 2026-04-30
> **최종 업데이트**: 2026-05-01 (Instruction 탭 기반 산출물 플레이스홀더 매핑 반영)
> **버전**: v1.3

---

## 목차

1. [작업 컨텍스트](#1-작업-컨텍스트)
2. [워크플로우 정의](#2-워크플로우-정의)
3. [구현 스펙](#3-구현-스펙)

---

## 1. 작업 컨텍스트

### 1.1 배경 및 목적

아마존 판매 실적을 기반으로 고객사별 판매수수료를 정산하고, 관련 보고서 및 인보이스를 자동 생성·발송·저장하는 일련의 반복 업무를 자동화한다. 월별 정산 주기에 따라 사람이 수동으로 처리하던 프로세스를 에이전트가 대체하며, 오류 발생 시 로그를 남기고 사람의 검토를 요청하는 에스컬레이션 구조를 포함한다.

### 1.2 처리 범위

| 구분 | 내용 |
|------|------|
| 처리 주기 | 월 1회 (정산월 기준 YYYYMM 입력) |
| 처리 대상 | 계약 유효 고객사 전체 (현재 약 13개사) |
| 처리 방식 | 고객사별 병렬 동시 실행 |
| 실패 격리 | 고객사 단위 격리 — A사 실패 시 B·C사는 계속 진행 |

### 1.3 입력

| 입력 | 형태 | 설명 |
|------|------|------|
| `YYYYMM` | 문자열 | 정산 대상 기간 (예: `202504`) |

> 고객사 목록, 계약 정보, 주문 데이터, 환율 등은 모두 DB에서 SP를 통해 조회한다. 별도 파일 입력 없음.

**실행 방식**: Claude Code CLI 대화창에서 사용자가 YYYYMM을 입력하면 오케스트레이터가 실행을 시작한다.

**재실행 처리**: 동일 YYYYMM 입력 시 `/output/{YYYYMM}/` 존재 여부를 먼저 확인한다. 기존 처리 내역이 있으면 Claude 대화창에서 사용자에게 선택을 요청한다.
- 옵션 A: 실패 고객사만 재처리 (`invoice.pdf` 미존재 고객사만 STEP 3부터 재실행)
- 옵션 B: 전체 재처리 (모든 고객사 재실행, 기존 파일 덮어쓰기)

### 1.4 출력

| 산출물 | 형식 | 설명 |
|--------|------|------|
| Revenue Report | PDF | 고객사별 매출 요약 보고서 |
| Transaction Report | Excel (.xlsx) | 고객사별 주문 트랜잭션 상세 |
| Selling Fee Invoice | PDF | 고객사별 판매수수료 청구서 |
| Gmail Draft | 이메일 초안 | 위 3개 파일 첨부, 고객사당 1건 |
| Google Drive 저장 | 파일 | 루트 폴더(`15_PI1CkFgwz6l6vbr_qauGcgBRy_scLb`) 내 `{YYYYMM}` 폴더에 저장. 오류 시 `Error` 폴더에 저장 |
| Processing Log | DB 레코드 | 단계별 처리 결과 (`SP_Insert_Processing_Log`) |
| 에스컬레이션 Gmail Draft | 이메일 초안 | FAILED 고객사 발생 시 처리 중단 사유·필요 조치 명시, 수신자: 내부 담당자 3명 |

### 1.5 제약조건

- Google Drive 저장 시 기존 파일 덮어쓰기 (버전 관리 없음)
- 메일은 Draft 생성까지만 수행 (자동 발송 아님 — 사람이 검토 후 발송)
- 동시 실행 수 제한 없음 (13개사 전체 병렬)
- SP 외부에서 DB를 직접 조작하지 않음 (모든 DB 접근은 SP 경유)
- 실행 환경: Windows (Python 3.11+, Google API 연동)
- Google Drive 루트 폴더: `15_PI1CkFgwz6l6vbr_qauGcgBRy_scLb` (고정)
- Drive 폴더 구조: `{루트}/{YYYYMM}/` — YYYYMM 폴더 없으면 자동 생성
- Drive 오류 시: `{루트}/Error/` 폴더에 결과물·로그 저장 (재시도 없음)
- 고객사별 처리 타임아웃: 30분 (코드 내 상수로 고정)
- Gmail Draft 생성 주체: `info@forsit.co.kr` (서비스 계정 + Domain-Wide Delegation 설정 필요)
- 에스컬레이션 Draft 수신자: `dayeon@forsit.co.kr; allan@forsit.co.kr; sungho@forsit.co.kr` (코드 내 고정)
- Google Drive 타입: google 전용 (Shared Drive 없음)

### 1.6 용어 정의

| 용어 | 정의 |
|------|------|
| `PerformanceUSD` | OrderMeasure 룰 적용 후 산정된 고객사 매출 실적 (USD) |
| `OrderMeasure` | 고객사별 실적 집계 시 포함/제외할 금액 항목 정의 (`+`/`-`) |
| 초과누진 셀링피 | 실적 구간별로 다른 요율을 적용하여 누적 계산하는 방식 |
| `sheet_key` | `Fixed` 테이블의 컬럼. 고객사별 산출물 템플릿 스프레드시트 연동 키 |
| `mail_type` | 메일 수신 담당자 유형 분류 (Contact_mail 테이블) |
| 정산월 | 처리 대상 기간 (`YYYYMM`) |
| 익월 초일 환율 | 정산월 다음 달 1일 기준 환율 (인보이스 통화 환산 기준) |

---

## 2. 워크플로우 정의

### 2.1 전체 흐름 개요

```
[입력] YYYYMM
    │
    ▼
[STEP 1] 처리 대상 고객사 조회          ← 스크립트 (SP 호출)
    │
    ▼
[STEP 2] 고객사별 병렬 처리 시작        ← 오케스트레이터가 Task 병렬 실행
    │
    ├─ [Client A] ──┐
    ├─ [Client B] ──┤  ← 각각 독립 서브에이전트 실행
    └─ [Client C] ──┘
            │
            ▼ (각 고객사 내부 순차 처리)
        [STEP 3]  주문 조회 및 USD 환산
        [STEP 4]  PerformanceUSD 산정
        [STEP 5]  유효 계약 및 요율 조회
        [STEP 6]  초과누진 셀링피 계산
        [STEP 7]  청구 통화 결정 및 환율 적용
        [STEP 8]  산출물 생성 (Revenue Report / Transaction Report / Invoice)
        [STEP 9]  Google Drive 저장
        [STEP 10] Gmail Draft 생성
        [STEP 11] Processing Log 저장
            │
            ▼
[STEP 12] 전체 처리 결과 집계 및 요약   ← 오케스트레이터
```

### 2.2 단계별 상세 정의

---

#### STEP 1. 처리 대상 고객사 조회

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Get_AmzOrder_By_Period` → 주문 존재 고객사 목록 추출 |
| **출력** | `/output/{YYYYMM}/clients.json` — `[{company_code, company_name}, ...]` |
| **성공 기준** | 1개 이상의 고객사가 반환됨 |
| **검증 방법** | 규칙 기반 — 결과 배열 길이 > 0 |
| **실패 처리** | 에스컬레이션 — 고객사 목록이 비어있으면 전체 중단 후 사람에게 확인 요청 |

**재실행 사전 확인 (STEP 1 실행 전)**:
1. `/output/{YYYYMM}/` 디렉터리 존재 여부 확인
2. 존재 시 → Claude 대화에서 사용자에게 선택 요청
3. 실패 고객사 판단: `/output/{YYYYMM}/{company_code}/invoice.pdf` 미존재 = 미완료
4. 전체 재처리 선택 시 → 기존 고객사 디렉터리 파일 덮어쓰기로 진행

---

#### STEP 2. 고객사별 병렬 실행 시작

| 항목 | 내용 |
|------|------|
| **처리 주체** | 오케스트레이터 (메인 에이전트) |
| **동작** | `clients.json`을 읽어 각 고객사에 대해 `client-processor` 서브에이전트를 동시 실행 (`Task` 병렬 호출) |
| **데이터 전달** | `{YYYYMM, company_code, company_name}` 프롬프트 인라인 전달 |
| **실패 격리** | 개별 Task 실패는 해당 고객사만 실패 처리; 나머지 Task는 계속 진행 |

---

#### STEP 3. 주문 조회 및 USD 환산

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Get_AmzOrder_By_Client` → `SP_Convert_Order_Amount_To_USD` |
| **출력** | `/output/{YYYYMM}/{company_code}/orders_usd.json` |
| **성공 기준** | 주문 레코드 1건 이상, 모든 행에 FXRate 및 USD 환산값 존재 |
| **검증 방법** | 스키마 검증 — 필수 필드 존재, NULL 체크 |
| **실패 처리** | 에스컬레이션 — 환율 데이터 누락 시 `SP_Get_ExchangeRate_Fallback` 재시도 1회 → 그래도 없으면 에스컬레이션 |

---

#### STEP 4. PerformanceUSD 산정

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Get_OrderMeasure_By_Client` → `SP_Calc_Order_Performance_By_Measure` |
| **출력** | `/output/{YYYYMM}/{company_code}/performance.json` — `{performance_usd: decimal}` |
| **ERD 연계** | SP 실행 결과는 `AmzOrder.PerformanceUSD`, `AmzOrder.PerformanceType` 컬럼에 저장됨 |
| **성공 기준** | `PerformanceUSD` 값이 존재하고 0 이상 |
| **검증 방법** | 스키마 검증 + 규칙 기반 (음수 여부 확인) |
| **실패 처리** | 에스컬레이션 — OrderMeasure 룰 미정의 고객사는 처리 중단 후 확인 요청 |

> **LLM 판단 개입 시점**: PerformanceUSD가 전월 대비 ±50% 이상 이상치일 경우 경고 로그를 기록하고 처리를 계속 진행한다. 단, 전월 데이터가 없는 경우(신규 고객사 또는 해당 월 주문 없음)는 경고 로그만 기록하고 에스컬레이션 없이 계속 진행한다.

---

#### STEP 5. 유효 계약 및 요율 조회

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Get_Valid_Contract(@YYYYMM, @CompanyCode)` → `SP_Get_Selling_Fee_Rate(@ContractNumber)` |
| **출력** | `/output/{YYYYMM}/{company_code}/contract.json` — 계약번호, 계약 기간, 계약 상태<br>`/output/{YYYYMM}/{company_code}/rate.json` — 구간별 요율 배열 (`line_number`, `amount_from`, `amount_to`, `rate`) |
| **성공 기준** | 유효 계약 1건 존재, 요율 구간 1건 이상 |
| **검증 방법** | 스키마 검증 |
| **실패 처리** | 에스컬레이션 — 유효 계약 없음 또는 요율 미정의 시 해당 고객사 처리 중단 |

> **SP 파라미터 주의**: `SP_Get_Selling_Fee_Rate`는 `@CompanyCode`나 `@YYYYMM`이 아닌 **`@ContractNumber`** 를 입력받는다. `contract.json`에서 `contract_number`를 읽어 전달해야 한다.

---

#### STEP 6. 초과누진 셀링피 계산

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Calc_Tiered_Selling_Fee(@ContractNumber, @PerformanceUSD)` |
| **출력** | `/output/{YYYYMM}/{company_code}/selling_fee.json` — 구간별 `AppliedAmountUSD`, `SellingFeeUSD`, `rate` |
| **성공 기준** | 구간별 계산 결과 합계 = 전체 수수료, 수수료 > 0 |
| **검증 방법** | 규칙 기반 — 구간 합산 검증 |
| **실패 처리** | 자동 재시도 1회 → 실패 시 에스컬레이션 |

> **Invoice 적용 요율 산출**: `selling_fee.json`에서 `AppliedAmountUSD > 0`인 구간의 `rate`만 추출하여 `,`로 연결한다. (전체 요율 구간이 아닌 실제 적용 구간만 표시)

---

#### STEP 7. 청구 통화 결정 및 익월 환율 적용

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Get_Fixed_Currency` → `SP_Get_ExchangeRate_NextMonth` → `SP_Get_ExchangeRate_Fallback` (fallback) → `SP_Calc_Selling_Fee_Client` (최종 fallback) |
| **출력** | `/output/{YYYYMM}/{company_code}/billing.json` — 청구 통화, 환율, 최종 청구 금액 |
| **billing.json 필드** | `PerformanceUSD`, `BillingCurrency`, `USDKRWRate`, `SellingFeeUSD`, `SellingFeeKRW`, `VAT`, `TotalAmount` |
| **성공 기준** | 청구 통화 존재, 환율 존재, 최종 금액 > 0 |
| **검증 방법** | 스키마 검증 + 규칙 기반 |
| **실패 처리** | Fallback 환율 자동 적용 → 그래도 없으면 `SP_Calc_Selling_Fee_Client`로 통합 계산 → 모두 실패 시 에스컬레이션 |

> **Fallback 환율 정책**: `SP_Get_ExchangeRate_Fallback(@BaseDate DATE, @Currency CHAR(3))`은 기준일(익월 초일) 환율이 없을 경우 **기준일 이후 가장 빠른 날짜**의 환율을 반환한다.

> **`SP_Calc_Selling_Fee_Client` 최종 Fallback**: `@YYYYMM`, `@CompanyCode` 입력으로 STEP 3~7 전체를 내부에서 처리하며 환율 포함 최종 청구 금액을 반환한다. 개별 환율 SP가 모두 빈 결과를 반환할 때 이 SP를 호출하여 `billing.json`을 구성한다.

---

#### STEP 8. 산출물 생성

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (파일 생성) + LLM (내용 검토) |
| **사용 SP** | **Invoice**: `billing.json` (STEP 7 산출물) + `selling_fee.json` (STEP 6 산출물)<br>**Transaction Report**: `SP_Get_AmzOrder_By_Client`, `SP_Get_Client_Info`<br>**Revenue Report**: `SP_Get_AmzOrder_By_Client`, `SP_Get_OrderMeasure_By_Client`, `SP_Get_Client_Info`<br>**공통**: `SP_Get_Client_Info` (회사명·주소·사업자번호·대표자명·별칭) |
| **입력** | `/output/{YYYYMM}/{company_code}/` 하위 JSON 파일들 |
| **출력** | `/output/{YYYYMM}/{company_code}/revenue_report.pdf` |
| | `/output/{YYYYMM}/{company_code}/transaction_report.xlsx` |
| | `/output/{YYYYMM}/{company_code}/invoice.pdf` |
| **성공 기준** | 3개 파일 모두 생성됨, 파일 크기 > 0 |
| **검증 방법** | 규칙 기반 (파일 존재·크기) + LLM 자기 검증 (수치 일관성, 고객사명·기간 정확성) |
| **실패 처리** | 자동 재시도 1회 → 실패 시 에스컬레이션 |

> **LLM 판단 개입 시점**: 생성된 PDF/Excel의 핵심 수치(PerformanceUSD, 청구금액, 고객사명, 정산 기간)가 source JSON과 일치하는지 자기 검증 수행.

> **파일 생성 방식**: Google Sheets 템플릿 스프레드시트 (`192bh56QrTjBbv7Gwk9dkdRZRhBqr4hW70tZCqQOFtJY`) 내 해당 탭을 임시 복사하고 Sheets API로 데이터를 주입한 뒤, Drive API `export` 기능으로 PDF(Invoice, Revenue Report) 또는 xlsx(Transaction Report)로 다운로드하여 로컬에 저장한다. 처리 완료 후 임시 시트는 삭제한다. Invoice는 `billing.json`의 청구 통화에 따라 `Invoice_Template_KRW` 또는 `Invoice_Template_USD` 탭을 사용한다.

---

#### STEP 9. Google Drive 저장

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | 없음 (Drive 경로 고정) |
| **루트 폴더 ID** | `15_PI1CkFgwz6l6vbr_qauGcgBRy_scLb` |
| **인증** | `credential.json` |
| **동작** | ① 루트 폴더 내 `{YYYYMM}` 폴더 존재 확인 → 없으면 생성<br>② 3개 파일을 Drive 파일명 규칙으로 업로드 (기존 파일 덮어쓰기)<br>③ 오류 발생 시 → `Error` 폴더에 결과물 저장 + 에러 로그 파일(`{company_code}_error.log`) 생성 |
| **Drive 파일명 규칙** | `Revenue_Report_{CompanyCode}_{YYYYMM}.pdf`<br>`Transaction_Report_{CompanyCode}_{YYYYMM}.xlsx`<br>`Invoice_{CompanyCode}_{YYYYMM}.pdf` |
| **성공 기준** | 3개 파일 모두 `{YYYYMM}` 폴더에 업로드 완료 |
| **검증 방법** | 규칙 기반 — Drive API 업로드 응답 상태 코드 확인 |
| **실패 처리** | 재시도 없음 → 즉시 `Error` 폴더로 전환 후 에스컬레이션 |

**에러 로그 파일 형식** (`{루트}/Error/{company_code}_error.log`):
```
company_code  : {company_code}
company_name  : {company_name}
period        : {YYYYMM}
error_step    : STEP 9 - Google Drive Upload
error_message : {에러 상세 내용}
timestamp     : {ISO 8601}
```

---

#### STEP 10. Gmail Draft 생성

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Get_Contact_Mail(@CompanyCode, @MailType)` |
| **MailType 값** | `'invoice'` (상업용 수신자 조회 기준) |
| **동작** | 고객사당 1건의 Gmail Draft 생성 (고정 템플릿 변수 치환), 3개 파일 첨부 |
| **성공 기준** | Draft 생성 완료, 수신자·첨부파일 확인 |
| **검증 방법** | 규칙 기반 (Draft ID 존재, 첨부 파일 수 = 3) |
| **실패 처리** | 자동 재시도 1회 → 실패 시 스킵 + 로그 (메일은 선택적 단계로 간주, 파일은 이미 Drive에 저장됨) |

**메일 제목·본문 (고정 템플릿)**:

```
제목: [아마존_Invoice] {company_name} Selling Fee invoice {YYYYMM}

안녕하세요 폴싯 빌링팀입니다.

판매수수료 {YYYYMM} invoice를 송부드립니다.

폴싯 빌링팀 드림
```

> 변수: `{company_name}` = 고객사명, `{YYYYMM}` = 정산월. 스크립트에서 직접 치환하며 LLM 개입 없음.

---

#### STEP 11. Processing Log 저장

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **사용 SP** | `SP_Insert_Processing_Log` |
| **동작** | 각 단계별 성공/실패 결과를 DB에 기록 (단계마다 호출) |
| **성공 기준** | 로그 레코드 저장 완료 |
| **검증 방법** | 규칙 기반 — SP 반환 결과 확인 |
| **실패 처리** | 스킵 + 콘솔 출력 (로그 저장 실패가 전체 흐름을 막지 않음) |

---

#### STEP 12. 전체 결과 집계 (오케스트레이터)

| 항목 | 내용 |
|------|------|
| **처리 주체** | LLM (오케스트레이터) |
| **동작** | 병렬 Task 완료 후 성공/실패/에스컬레이션 고객사 목록 취합 및 요약 리포트 출력 |
| **출력** | 콘솔 요약 (성공 N건, 실패 N건, 에스컬레이션 필요 목록) |
| **성공 기준** | 전체 고객사에 대한 처리 결과가 수집됨 |

---

### 2.3 분기 조건 및 상태 전이

```
각 고객사 처리 상태:
  PENDING → RUNNING → SUCCESS
                    → FAILED (에스컬레이션)
                    → PARTIAL (일부 단계 스킵, 로그 기록)
```

| 분기 조건 | 처리 방식 |
|-----------|----------|
| 환율 데이터 없음 | Fallback SP 호출 → 없으면 FAILED + 에스컬레이션 Gmail Draft + 콘솔 출력 |
| OrderMeasure 미정의 | FAILED + 에스컬레이션 Gmail Draft + 콘솔 출력 |
| 유효 계약 없음 | FAILED + 에스컬레이션 Gmail Draft + 콘솔 출력 |
| PerformanceUSD 이상치 (전월 있음) | 경고 로그 기록 + 처리 계속 진행 |
| PerformanceUSD 이상치 (전월 없음) | 경고 로그만 기록 + 처리 계속 진행 (에스컬레이션 없음) |
| 파일 생성 실패 | 재시도 1회 → FAILED + 에스컬레이션 |
| Drive 저장 실패 | 즉시 `Error` 폴더에 결과물·로그 저장 → 에스컬레이션 |
| Gmail Draft 실패 | 재시도 1회 → PARTIAL (스킵 + 로그) |

### 2.4 LLM 판단 영역 vs 코드 처리 영역 요약

| LLM 판단 | 스크립트 처리 |
|----------|-------------|
| PerformanceUSD 이상치 감지 (경고 로그 기록) | 모든 SP 호출 |
| 산출물 수치 일관성 자기 검증 | 파일 생성 (PDF, Excel) |
| 전체 처리 결과 요약 | Google Drive 업로드 |
| | Gmail Draft 생성 (고정 템플릿 변수 치환, LLM 불필요) |
| | Processing Log 저장 |

---

## 3. 구현 스펙

### 3.1 폴더 구조

```
/project-root
  ├── CLAUDE.md                                    # 메인 에이전트 지침 (오케스트레이터)
  ├── /.claude
  │   ├── /skills
  │   │   ├── /db-caller                           # DB SP 호출 공통 스킬
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       └── call_sp.py                   # SP 호출 래퍼
  │   │   ├── /report-generator                    # 산출물 파일 생성 스킬
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       ├── generate_revenue_pdf.py      # Revenue Report PDF 생성
  │   │   │       ├── generate_transaction_xlsx.py # Transaction Report Excel 생성
  │   │   │       └── generate_invoice_pdf.py      # Invoice PDF 생성
  │   │   ├── /drive-uploader                      # Google Drive 업로드 스킬
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       └── upload_to_drive.py
  │   │   ├── /gmail-drafter                       # Gmail Draft 생성 스킬
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       └── create_gmail_draft.py
  │   │   └── /process-logger                      # 처리 로그 스킬
  │   │       ├── SKILL.md
  │   │       └── /scripts
  │   │           └── insert_log.py
  │   └── /agents
  │       └── /client-processor                    # 고객사별 처리 서브에이전트
  │           └── AGENT.md
  ├── /output
  │   └── /{YYYYMM}
  │       ├── clients.json                         # STEP 1 산출물
  │       └── /{company_code}
  │           ├── orders_usd.json                  # STEP 3 산출물
  │           ├── performance.json                 # STEP 4 산출물
  │           ├── contract.json                    # STEP 5 산출물
  │           ├── selling_fee.json                 # STEP 6 산출물
  │           ├── billing.json                     # STEP 7 산출물
  │           ├── revenue_report.pdf               # STEP 8 산출물
  │           ├── transaction_report.xlsx          # STEP 8 산출물
  │           └── invoice.pdf                      # STEP 8 산출물
  └── /docs
      ├── db_schema.md                             # DB 테이블 명세
      └── sp_reference.md                          # SP 목록 및 파라미터 참조
```

### 3.2 CLAUDE.md 핵심 섹션 목록

| 섹션 | 내용 요약 |
|------|----------|
| 역할 | 오케스트레이터 — 전체 워크플로우 조율, 서브에이전트 병렬 실행 |
| 실행 트리거 | 사용자가 `YYYYMM` 입력 시 시작 |
| STEP 1 지침 | `db-caller` 스킬로 고객사 목록 조회 → `clients.json` 저장 |
| STEP 2 지침 | `client-processor` 서브에이전트를 고객사 수만큼 병렬 Task 실행 |
| STEP 12 지침 | 모든 Task 완료 후 결과 집계, 에스컬레이션 목록 사람에게 보고 |
| 에스컬레이션 규칙 | 에스컬레이션 발생 시 처리 중단 사유와 필요한 확인 사항을 명확히 제시 |
| 데이터 전달 규칙 | 중간 산출물은 `/output/`에 저장, 파일 경로만 서브에이전트에 전달 |

### 3.3 에이전트 구조

```
CLAUDE.md (오케스트레이터)
    │
    ├── STEP 1: db-caller 스킬 직접 사용
    │
    ├── STEP 2~11: client-processor 서브에이전트 × 13개 병렬 실행
    │               └── 내부에서 5개 스킬 순차 호출
    │
    └── STEP 12: 결과 집계 및 요약 출력
```

**서브에이전트 분리 근거**: STEP 2~11은 고객사별로 독립 실행되며, 각 실행마다 DB 조회 → 계산 → 파일 생성 → 외부 API 호출의 복잡한 컨텍스트를 가진다. 오케스트레이터의 컨텍스트 윈도우를 13개 고객사 처리 내용으로 오염시키지 않기 위해 서브에이전트로 분리한다.

### 3.4 서브에이전트 정의: `client-processor`

| 항목 | 내용 |
|------|------|
| **역할** | 단일 고객사에 대한 STEP 3~11 전체 순차 처리 |
| **트리거 조건** | 오케스트레이터가 `client-processor`를 Task로 호출할 때 |
| **입력** | `{YYYYMM, company_code, company_name}` (프롬프트 인라인) |
| **출력** | `/output/{YYYYMM}/{company_code}/` 하위 모든 파일 + Processing Log DB 기록 |
| **참조 스킬** | `db-caller`, `report-generator`, `drive-uploader`, `gmail-drafter`, `process-logger` |
| **데이터 전달** | 단계 간 JSON 파일 경로 참조 (`/output/{YYYYMM}/{company_code}/`) |
| **실패 시** | 해당 고객사 상태를 FAILED로 기록하고 오케스트레이터에 실패 사유 반환 |

### 3.5 스킬 목록

| 스킬명 | 역할 | 트리거 조건 |
|--------|------|------------|
| `db-caller` | SP 호출 및 결과 JSON 저장 | 모든 DB 조회/계산 단계 (STEP 1, 3, 4, 5, 6, 7) |
| `report-generator` | Revenue Report(PDF), Transaction Report(Excel), Invoice(PDF) 파일 생성 | STEP 8: SP에서 데이터 조회 완료 후 |
| `drive-uploader` | Google Drive에 파일 업로드, 기존 파일 덮어쓰기 | STEP 9: 3개 산출물 파일 생성 완료 후 |
| `gmail-drafter` | Gmail Draft 생성 및 파일 첨부 | STEP 10: Drive 저장 완료 후 |
| `process-logger` | `SP_Insert_Processing_Log` 호출로 각 단계 결과 DB 기록 | 각 단계 완료/실패 직후 |

### 3.6 주요 산출물 파일 형식

모든 산출물 파일은 **Google Sheets 템플릿 스프레드시트**를 기반으로 생성한다.

- **템플릿 스프레드시트 ID**: `192bh56QrTjBbv7Gwk9dkdRZRhBqr4hW70tZCqQOFtJY`
- **인증 파일**: `credential.json` (프로젝트 루트, `.gitignore` 대상)

| 파일 | 형식 | 템플릿 탭명 | 데이터 소스 SP |
|------|------|------------|--------------|
| `invoice.pdf` | PDF | `Invoice_Template_KRW` (원화) / `Invoice_Template_USD` (미화) | `billing.json`(STEP 7), `selling_fee.json`(STEP 6), `SP_Get_Client_Info` |
| `transaction_report.xlsx` | Excel | `Transaction_Report` | `SP_Get_AmzOrder_By_Client`, `SP_Get_Client_Info` |
| `revenue_report.pdf` | PDF | `Revenue_Report` | `SP_Get_AmzOrder_By_Client`, `SP_Get_OrderMeasure_By_Client`, `SP_Get_Client_Info` |

**생성 방식**: Sheets API로 해당 탭을 임시 복사 → 데이터 주입 → Drive API `export` 기능으로 PDF/xlsx 다운로드 → 로컬 저장 후 임시 시트 삭제.

**Invoice 통화 선택**: `billing.json`의 청구 통화에 따라 `Invoice_Template_KRW` 또는 `Invoice_Template_USD` 탭 사용.

**파일명 구분**:

| 구분 | 파일명 형식 | 예시 |
|------|-----------|------|
| 로컬 임시 저장 | snake_case 고정명 | `invoice.pdf`, `transaction_report.xlsx`, `revenue_report.pdf` |
| Drive 업로드 | `{Type}_{CompanyCode}_{YYYYMM}.{ext}` | `Invoice_ABC_202504.pdf` |

#### 플레이스홀더 매핑

스프레드시트 Instruction 탭 기준 각 탭의 플레이스홀더와 데이터 소스를 정의한다.

**Invoice (KRW / USD 공통)**

| 플레이스홀더 | 출처 | 비고 |
|------------|------|------|
| `[회사명]` | `Client.company_name` | |
| `[사업자번호]` | `Client.business_number` | |
| `[대표자명]` | `Client.representative` | |
| `[인보이스 청구년월]` | 입력값 YYYYMM | `YYYY/MM` 형식 |
| `[인보이스번호]` | 생성 규칙 | `{Client.alias}_invoice_amz_selling_{YYYY-MM}` |
| `[인보이스일자]` | 입력값 YYYYMM | 해당 월 초일 (`YYYY-MM-01`) |
| `[지급기한]` | 계산값 | `[인보이스일자]` + 14일 |
| `[USD to KRW 환율]` | `billing.json`.`USDKRWRate` | **KRW 탭 전용** (USD 탭에는 해당 필드 없음) |
| `[서비스 기간]` | 입력값 YYYYMM | `YYYY-MM-01 ~ YYYY-MM-말일` |
| `[주문 실적]` | `billing.json`.`PerformanceUSD` | 띄어쓰기 있음 — 템플릿 플레이스홀더와 정확히 일치 필요 |
| `[적용 요율]` | `selling_fee.json` | `AppliedAmountUSD > 0`인 구간의 `rate`만 추출, `,` 연결 |
| `[셀링피]` | `billing.json`.`SellingFeeUSD` | 청구 통화(KRW/USD) 무관하게 항상 USD 금액 |

**Transaction Report**

| 플레이스홀더 / 범위 | 출처 | 비고 |
|-------------------|------|------|
| `[회사명]` | `Client.company_name` | |
| `[주소]` | `Client.address` | |
| `[사업자번호]` | `Client.business_number` | |
| `[대표자명]` | `Client.representative` | |
| 데이터 범위 `B11:T` | `SP_Get_AmzOrder_By_Client` | 주문 트랜잭션 전체 행 삽입 |

**Revenue Report**

| 플레이스홀더 / 범위 | 출처 | 비고 |
|-------------------|------|------|
| `[회사명]` | `Client.company_name` | |
| `[주소]` | `Client.address` | |
| `[사업자번호]` | `Client.business_number` | |
| `[대표자명]` | `Client.representative` | |
| `[별칭]` | `Client.alias` | |
| `[YYYYMM]` | 입력값 YYYYMM | 헤더 `{별칭} - {YYYYMM}` 형식에 사용 |
| 데이터 범위 `A20:D` | `SP_Get_AmzOrder_By_Client` + `SP_Get_OrderMeasure_By_Client` | ASIN으로 GROUP BY 후 QTY SUM, Revenue(USD) = OrderMeasure 룰 적용 후 `SUM(per-order Performance)` — `SP_Get_AmzOrder_By_Client`는 `PerformanceUSD` 컬럼을 반환하지 않으므로 Python에서 직접 계산 |

### 3.7 외부 API 의존성

| 대상 | 용도 | 사용 스킬 |
|------|------|----------|
| MS SQL Server | SP 실행 및 결과 조회 | `db-caller` |
| Google Drive API | 파일 업로드 | `drive-uploader` |
| Gmail API | Draft 생성 및 파일 첨부 | `gmail-drafter` |
| Google Sheets API | 산출물 템플릿 탭 복사·데이터 주입 (Invoice/Transaction/Revenue) | `report-generator` |

### 3.8 기술 스택

| 레이어 | 선택 |
|--------|------|
| 에이전트 프레임워크 | Claude Code CLI + Python 스크립트 혼용 |
| Python 버전 | 3.11+ |
| 패키지 관리 | `requirements.txt` |
| DB 연결 | `pyodbc` (ODBC Driver for SQL Server) |
| PDF/Excel 생성 | Google Sheets API (템플릿 탭 복사·데이터 주입) + Drive API (`export` 기능으로 PDF/xlsx 다운로드) |
| Google API 클라이언트 | `google-api-python-client`, `google-auth` |
| 환경변수 | `python-dotenv` (`.env` 파일) |
| 실행 환경 | Windows, Python 3.11+ |

---

### 3.9 Google API 인증 설정

| 항목 | 내용 |
|------|------|
| 인증 방식 | 서비스 계정 (Service Account) |
| Credentials 파일 | `credential.json` (프로젝트 루트, `.gitignore` 대상) |
| `.env` 설정값 | `GOOGLE_CREDENTIALS_FILE=credential.json` (**단수**, `credentials.json` 복수 아님) |
| Gmail 접근 | **Domain-Wide Delegation** 설정 필수 (Google Workspace 관리콘솔에서 서비스 계정에 `https://www.googleapis.com/auth/gmail.compose` 스코프 부여) |
| Gmail Draft 생성 주체 | `info@forsit.co.kr` (해당 계정을 impersonate하여 Draft 생성) |
| Drive/Sheets 접근 | 서비스 계정 직접 접근 (Drive 폴더에 서비스 계정 이메일 공유 필요) |
| Gmail 미설정 시 | `unauthorized_client` 오류 발생 → STEP 10 PARTIAL 처리 (파일은 Drive에 저장 완료 상태) |

---

### 3.10 재실행 전략

| 상황 | 처리 방식 |
|------|-----------|
| `/output/{YYYYMM}/` 미존재 | 정상 최초 실행 |
| `/output/{YYYYMM}/` 존재 | Claude 대화에서 사용자 선택 질문 |
| 실패 고객사만 재처리 | `invoice.pdf` 미존재 고객사만 STEP 3부터 재실행 |
| 전체 재처리 | 모든 고객사 STEP 3부터 재실행 (기존 파일 덮어쓰기) |
| 완료 판단 기준 | `invoice.pdf` 존재 여부 |
| 크래시 후 복구 | 재실행 시 파일 존재 기반 자동 건너뛰기와 동일 메커니즘 적용 |

---

### 3.11 에스컬레이션 Gmail Draft 상세

| 항목 | 내용 |
|------|------|
| 수신자 | `dayeon@forsit.co.kr; allan@forsit.co.kr; sungho@forsit.co.kr` (코드 내 고정) |
| 생성 주체 계정 | `info@forsit.co.kr` |
| 트리거 | FAILED 상태 고객사 발생 시 (OrderMeasure 미정의, 유효 계약 없음, 환율 없음, 파일 생성 실패 등) |
| Draft 내용 | 고객사명, 실패 단계, 실패 사유, 사람에게 필요한 조치 사항 |
| 상업용 Draft와 구분 | 수신자 상이 (내부 담당자 vs 고객사 담당자) |
| 전체 에스컬레이션 요약 | STEP 12에서 오케스트레이터가 에스컬레이션 고객사 목록을 콘솔에도 출력 |

---

### 3.12 Gmail 메일 템플릿

템플릿은 고정값이며 코드 내에 직접 정의한다. Google Sheets 조회 불필요.

**제목**: `[아마존_Invoice] {company_name} Selling Fee invoice {YYYYMM}`

**본문**:
```
안녕하세요 폴싯 빌링팀입니다.

판매수수료 {YYYYMM} invoice를 송부드립니다.

폴싯 빌링팀 드림
```

| 변수 | 치환값 |
|------|--------|
| `{company_name}` | `SP_Get_Contact_Mail` 반환 고객사명 |
| `{YYYYMM}` | 정산월 입력값 |

---

### 3.13 미구현 범위 (향후 확장)

| 항목 | 관련 SP | 비고 |
|------|---------|------|
| 자동전표 연동 | `SP_Get_Amaranth10_Journal_Data` | ERP 연동 준비 완료, 구현 미착수 |
| 재정산 초기화 | `SP_Reset_Selling_Fee_Process` | 수동 재정산 필요 시 별도 실행 |
| 처리 이력 조회 | `SP_Get_Processing_Log` | 모니터링 UI 연동 시 활용 |
| 정산 오류 검증 | `SP_Validate_Selling_Fee_Process` | 선택적 사전 검증 단계로 추가 가능 |
| 기간 전체 실적 산정 | `SP_Calc_Order_Performance_Period` | 전체 고객사 일괄 처리 시 활용 가능 |
| 기간 전체 셀링피 계산 | `SP_Calc_Selling_Fee_Period` | 전체 고객사 일괄 셀링피 계산 |
| 고객사 정보 조회 | `SP_Get_Client_Info` | 필요 시 company_name 등 기본 정보 확인 |

---

## 부록: SP-워크플로우 매핑

| STEP | SP | 역할 |
|------|----|------|
| 1 | `SP_Get_AmzOrder_By_Period` | 처리 대상 고객사 목록 추출 |
| 3 | `SP_Get_AmzOrder_By_Client` | 고객사 주문 조회 |
| 3 | `SP_Convert_Order_Amount_To_USD` | 주문 금액 USD 환산 (`AmzOrder.FXRate` 기준) |
| 3 | `SP_Get_ExchangeRate_Fallback` | 환율 fallback 조회 (`@BaseDate`, `@Currency`) |
| 4 | `SP_Get_OrderMeasure_By_Client` | 집계 룰 조회 |
| 4 | `SP_Calc_Order_Performance_By_Measure` | PerformanceUSD 산정 → `AmzOrder.PerformanceUSD` 저장 |
| 5 | `SP_Get_Valid_Contract` | 유효 계약 조회 (`@YYYYMM`, `@CompanyCode`) |
| 5 | `SP_Get_Selling_Fee_Rate` | 구간별 요율 조회 — **`@ContractNumber` 단일 파라미터** (`@CompanyCode` 아님) |
| 6 | `SP_Calc_Tiered_Selling_Fee` | 초과누진 셀링피 계산 (`@ContractNumber`, `@PerformanceUSD`) |
| 7 | `SP_Get_Fixed_Currency` | 청구 통화 조회 (`Fixed.currency`, `Fixed.vat`) |
| 7 | `SP_Get_ExchangeRate_NextMonth` | 익월 초일 환율 조회 |
| 7† | `SP_Calc_Selling_Fee_Client` | STEP 3~7 통합 계산 — 환율 포함 최종 청구 금액 반환. 개별 환율 SP 실패 시 최종 Fallback으로 사용 |
| 8 | `SP_Get_AmzOrder_By_Client` | Transaction Report 원본 데이터, Revenue Report ASIN 집계 기반 |
| 8 | `SP_Get_OrderMeasure_By_Client` | Revenue Report Revenue(USD) 계산용 OrderMeasure 룰 조회 — `SP_Get_AmzOrder_By_Client`는 `PerformanceUSD`를 반환하지 않으므로 Python에서 직접 계산 |
| 8 | `SP_Get_Client_Info` | 고객사 기본 정보 조회 (모든 산출물 공통) |
| 9 | _(SP 없음 — Drive 폴더 고정)_ | Drive `{YYYYMM}` 폴더 생성 후 파일명 규칙 적용 업로드 |
| 10 | `SP_Get_Contact_Mail` | 수신 이메일 조회 (`@MailType='invoice'`) |
| 전체 | `SP_Insert_Processing_Log` | 단계별 처리 로그 저장 |

> ※ `SP_Get_Revenue_Report_Data`, `SP_Get_Transaction_Report_Data`, `SP_Get_Invoice_Data`는 DB에 존재하지 않음 — 해당 SP 호출 시 오류 발생. 대신 위 SP 조합으로 처리.
