# API 엔드포인트 명세서 v2.1

## 1. API 목록

| API No | 내용 | 입력 파라메터 | Procedure |
|---|---|---|---|
| API-01 | 특정 기간 전체 주문 트랜잭션 조회 | `@YYYYMM` | `SP_Get_AmzOrder_By_Period` |
| API-02 | 특정 기간 + 고객사 주문 트랜잭션 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_AmzOrder_By_Client` |
| API-03 | 주문 트랜잭션 금액 항목 USD 환산 | `@YYYYMM`, `@CompanyCode` | `SP_Convert_Order_Amount_To_USD` |
| API-04 | 고객사별 주문 실적 집계 룰 조회 | `@CompanyCode` | `SP_Get_OrderMeasure_By_Client` |
| API-05 | OrderMeasure 기준 주문 실적 산정 | `@YYYYMM`, `@CompanyCode` | `SP_Calc_Order_Performance_By_Measure` |
| API-06 | 특정 기간 전체 고객사 주문 실적 산정 | `@YYYYMM` | `SP_Calc_Order_Performance_Period` |
| API-07 | 특정 기간 + 고객사 주문 실적 산정 | `@YYYYMM`, `@CompanyCode` | `SP_Calc_Order_Performance_Client` |
| API-08 | 익월 초일 환율 조회 | `@YYYYMM`, `@Currency` | `SP_Get_ExchangeRate_NextMonth` |
| API-09 | 환율 fallback 조회 | `@BaseDate`, `@Currency` | `SP_Get_ExchangeRate_Fallback` |
| API-10 | 고객사 정보 조회 | `@CompanyCode` | `SP_Get_Client_Info` |
| API-11 | 유효 계약 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Valid_Contract` |
| API-12 | 계약별 판매수수료 요율 조회 | `@ContractNumber` | `SP_Get_Selling_Fee_Rate` |
| API-13 | 초과누진 구간별 요율 계산 | `@ContractNumber`, `@PerformanceUSD` | `SP_Calc_Tiered_Selling_Fee` |
| API-14 | 고객사 청구 통화 조회 | `@CompanyCode` | `SP_Get_Fixed_Currency` |
| API-15 | 셀링피 계산 - 전체 고객사 | `@YYYYMM` | `SP_Calc_Selling_Fee_Period` |
| API-16 | 셀링피 계산 - 특정 고객사 | `@YYYYMM`, `@CompanyCode` | `SP_Calc_Selling_Fee_Client` |
| API-17 | Revenue Report 생성용 데이터 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Revenue_Report_Data` |
| API-18 | Transaction Report 생성용 데이터 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Transaction_Report_Data` |
| API-19 | Selling Fee Invoice 생성용 데이터 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Invoice_Data` |
| API-20 | Google Drive 저장 경로 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Drive_Output_Path` |
| API-21 | 고객사 담당자 이메일 조회 | `@CompanyCode`, `@MailType` | `SP_Get_Contact_Mail` |
| API-22 | 이메일 초안 생성용 데이터 조회 | `@YYYYMM`, `@CompanyCode`, `@MailType` | `SP_Get_Email_Draft_Data` |
| API-23 | 오류 검증 실행 | `@YYYYMM`, `@CompanyCode` | `SP_Validate_Selling_Fee_Process` |
| API-24 | 처리 로그 저장 | `@YYYYMM`, `@CompanyCode`, `@Step`, `@Status`, `@Message` | `SP_Insert_Processing_Log` |
| API-25 | 처리 이력 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Processing_Log` |
| API-26 | 재정산 대상 초기화 | `@YYYYMM`, `@CompanyCode` | `SP_Reset_Selling_Fee_Process` |
| API-27 | 자동전표 연동용 데이터 조회 | `@YYYYMM`, `@CompanyCode` | `SP_Get_Amaranth10_Journal_Data` |

---

## 2. 참조 테이블

| 테이블명 | 용도 |
|---|---|
| `AmzOrder` | 주문 트랜잭션 원천 데이터 |
| `OrderMeasure` | 고객사별 주문 실적 집계 룰 |
| `ExchangeRate` | 통화별 USD 환산 환율 |
| `Client` | 고객사 기본 정보 및 alias 매핑 |
| `Contract` | 고객사 계약 정보 |
| `Selling_Fee_Rate` | 계약별 판매수수료 요율 |
| `Fixed` | 고객사별 청구 통화, 서비스 유형, Drive sheet key |
| `Contact_mail` | 고객사 담당자 이메일 |
| `ProcessingLog` | 처리 이력 및 오류 로그 예정 테이블 |

---

## 3. 핵심 처리 흐름

```text
API-01 / API-02
주문 트랜잭션 조회

→ API-03
주문 금액 항목 USD 환산

→ API-04 / API-05
OrderMeasure 기준 주문 실적 산정

→ API-08 / API-09
환율 조회 및 fallback 처리

→ API-11 / API-12 / API-13
계약, 요율 조회 및 초과누진 계산

→ API-14 / API-15 / API-16
청구 통화 확인 및 셀링피 계산

→ API-17 / API-18 / API-19
Revenue Report, Transaction Report, Invoice 데이터 조회

→ API-20
Google Drive 저장 경로 조회

→ API-21 / API-22
담당자 이메일 조회 및 이메일 초안 데이터 생성

→ API-23 / API-24 / API-25
검증, 로그 저장, 이력 조회
```

---

## 4. 주요 API 상세

### API-01. 특정 기간 전체 주문 트랜잭션 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_AmzOrder_By_Period` |
| 입력 파라메터 | `@YYYYMM CHAR(6)` |
| 주요 테이블 | `AmzOrder` |
| 설명 | 선택된 기간의 전체 주문 트랜잭션을 조회한다. |

---

### API-02. 특정 기간 + 고객사 주문 트랜잭션 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_AmzOrder_By_Client` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `AmzOrder`, `Client` |
| 설명 | 선택된 기간과 고객사 기준으로 주문 트랜잭션을 조회한다. `AmzOrder.Client`와 `Client.alias`를 매핑한다. |

---

### API-03. 주문 트랜잭션 금액 항목 USD 환산

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Convert_Order_Amount_To_USD` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `AmzOrder`, `Client`, `ExchangeRate` |
| 설명 | 주문 금액 항목을 USD 기준으로 환산한다. USD 외 통화는 정산월 익월 초일 환율을 적용하며, 해당일 환율이 없으면 다음 영업일 환율을 적용한다. |

대상 금액 컬럼:

| 원천 컬럼 | USD 환산 컬럼 |
|---|---|
| `ItemPrice` | `ItemPriceUSD` |
| `ItemTax` | `ItemTaxUSD` |
| `ShippingPrice` | `ShippingPriceUSD` |
| `ShippingTax` | `ShippingTaxUSD` |
| `GiftWrapPrice` | `GiftWrapPriceUSD` |
| `GiftWrapTax` | `GiftWrapTaxUSD` |
| `ItemPromotionDiscount` | `ItemPromotionDiscountUSD` |
| `ShipPromotionDiscount` | `ShipPromotionDiscountUSD` |

---

### API-04. 고객사별 주문 실적 집계 룰 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_OrderMeasure_By_Client` |
| 입력 파라메터 | `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `OrderMeasure` |
| 설명 | 고객사별 주문 실적 산정 항목의 `+`, `-`, NULL 룰을 조회한다. |

---

### API-05. OrderMeasure 기준 주문 실적 산정

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Calc_Order_Performance_By_Measure` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `AmzOrder`, `Client`, `ExchangeRate`, `OrderMeasure` |
| 설명 | USD 환산 금액에 대해 `OrderMeasure`의 `+`, `-`, NULL 기준을 적용하여 주문 실적을 산정한다. |

계산 룰:

| OrderMeasure 값 | 처리 |
|---|---|
| `+` | 해당 USD 환산 금액을 더함 |
| `-` | 해당 USD 환산 금액을 차감 |
| NULL / 빈칸 | 계산에서 제외 |

---

### API-08. 익월 초일 환율 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_ExchangeRate_NextMonth` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@Currency CHAR(3)` |
| 주요 테이블 | `ExchangeRate` |
| 설명 | 정산월의 익월 초일 기준 환율을 조회한다. |

---

### API-09. 환율 fallback 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_ExchangeRate_Fallback` |
| 입력 파라메터 | `@BaseDate DATE`, `@Currency CHAR(3)` |
| 주요 테이블 | `ExchangeRate` |
| 설명 | 기준일 환율이 없을 경우 기준일 이후 가장 빠른 환율을 조회한다. |

---

### API-11. 유효 계약 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_Valid_Contract` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `Contract` |
| 설명 | 고객사 코드, 계약기간, 계약상태 기준으로 유효 계약을 조회한다. |

---

### API-13. 초과누진 구간별 요율 계산

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Calc_Tiered_Selling_Fee` |
| 입력 파라메터 | `@ContractNumber VARCHAR(50)`, `@PerformanceUSD DECIMAL(18,2)` |
| 주요 테이블 | `Selling_Fee_Rate` |
| 설명 | `rate_type`, `amount_from`, `amount_to`, `rate` 기준으로 초과누진 방식의 셀링피를 계산한다. 구간 경계는 1달러 단위 차이를 적용한다. |

---

### API-16. 셀링피 계산 - 특정 고객사

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Calc_Selling_Fee_Client` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `AmzOrder`, `Client`, `ExchangeRate`, `OrderMeasure`, `Contract`, `Selling_Fee_Rate`, `Fixed` |
| 설명 | 특정 고객사의 주문 실적, 계약, 요율, 청구 통화 기준을 종합하여 셀링피를 계산한다. |

청구 통화 처리:

| Fixed.currency | 처리 |
|---|---|
| `USD` | USD 기준 청구, VAT = 0 |
| `KRW` | USD 실적 기준 셀링피 계산 후 KRW 환산 청구, VAT 포함 |

---

### API-20. Google Drive 저장 경로 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_Drive_Output_Path` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `Fixed`, `Client` |
| 설명 | 생성 산출물 3종을 저장할 Google Drive 경로와 파일명을 반환한다. |

반환 컬럼:

| 컬럼명 | 타입 | 설명 |
|---|---|---|
| `company_code` | `varchar` | 고객사 코드 |
| `company_name` | `nvarchar` | 고객사명 |
| `period` | `char(6)` | 정산 기간 |
| `base_folder_path` | `nvarchar` | 고객사 기본 폴더 경로 |
| `period_folder_path` | `nvarchar` | 기간별 폴더 경로 |
| `revenue_report_path` | `nvarchar` | Revenue Report 저장 경로 |
| `transaction_report_path` | `nvarchar` | Transaction Report 저장 경로 |
| `invoice_path` | `nvarchar` | Invoice 저장 경로 |
| `sheet_key` | `nvarchar` | Google Sheet key |
| `drive_type` | `varchar` | Drive 유형 |

파일명 규칙:

```text
Revenue_Report_{CompanyCode}_{YYYYMM}.pdf
Transaction_Report_{CompanyCode}_{YYYYMM}.xlsx
Invoice_{CompanyCode}_{YYYYMM}.pdf
```

---

### API-21. 고객사 담당자 이메일 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_Contact_Mail` |
| 입력 파라메터 | `@CompanyCode VARCHAR(20)`, `@MailType VARCHAR(10)` |
| 주요 테이블 | `Contact_mail` |
| 설명 | 고객사 담당자 이메일을 조회한다. |

---

### API-22. 이메일 초안 생성용 데이터 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_Email_Draft_Data` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)`, `@MailType VARCHAR(10)` |
| 주요 테이블 | `Contact_mail`, 산출물 정보 |
| 설명 | Gmail Draft 생성을 위한 수신자, 제목, 본문, Drive 링크 정보를 반환한다. |

---

### API-23. 오류 검증 실행

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Validate_Selling_Fee_Process` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | 전체 관련 테이블 |
| 설명 | 주문, 환율, 집계 룰, 계약, 요율, 청구 통화, 메일 정보 등 필수 데이터 존재 여부를 검증한다. |

---

### API-24. 처리 로그 저장

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Insert_Processing_Log` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)`, `@Step VARCHAR(100)`, `@Status VARCHAR(20)`, `@Message NVARCHAR(MAX)` |
| 주요 테이블 | `ProcessingLog` 예정 |
| 설명 | 각 처리 단계별 정상, 오류, 스킵 이력을 저장한다. |

---

### API-25. 처리 이력 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_Processing_Log` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | `ProcessingLog` 예정 |
| 설명 | 고객사별 처리 상태, 실패 단계, 오류 메시지 등을 조회한다. |

---

### API-26. 재정산 대상 초기화

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Reset_Selling_Fee_Process` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | 계산 결과 및 로그 테이블 예정 |
| 설명 | 특정 기간과 고객사의 재정산을 위해 기존 처리 결과를 초기화한다. |

---

### API-27. 자동전표 연동용 데이터 조회

| 항목 | 내용 |
|---|---|
| Procedure | `SP_Get_Amaranth10_Journal_Data` |
| 입력 파라메터 | `@YYYYMM CHAR(6)`, `@CompanyCode VARCHAR(20)` |
| 주요 테이블 | Invoice 결과, `Client`, `Fixed` |
| 설명 | 향후 v2에서 Amaranth10 자동전표 연동을 위해 사용할 전표 데이터를 조회한다. 현재 버전에서는 제외한다. |
