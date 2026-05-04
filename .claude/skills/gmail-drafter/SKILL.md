# gmail-drafter 스킬

## 역할

고객사 발송용 Gmail Draft와 에스컬레이션용 Gmail Draft를 생성한다.
`info@forsit.co.kr` 계정으로 OAuth 2.0 인증 (첫 실행 시 브라우저 승인, 이후 `gmail_token.json` 재사용).

## 고객사 발송용 Draft

```bash
python .claude/skills/gmail-drafter/scripts/create_gmail_draft.py \
  --yyyymm 202504 \
  --company_code ABC \
  --company_name "홍길동상사" \
  [--base_dir output]
```

- 수신자: SP_Get_Contact_Mail(@CompanyCode, @MailType='invoice') 결과
- 첨부: revenue_report.pdf, transaction_report.xlsx, invoice.pdf
- 제목: `[아마존_Invoice] {company_name} Selling Fee invoice {YYYYMM}`
- 실패 시: 재시도 1회 → PARTIAL (스킵)

## 에스컬레이션 Draft

```bash
python .claude/skills/gmail-drafter/scripts/create_escalation_draft.py \
  --yyyymm 202504 \
  --company_code ABC \
  --company_name "홍길동상사" \
  --step "STEP 7 - 환율 조회" \
  --message "환율 데이터 없음: KRW 2025-05-01"
```

- 수신자: dayeon@forsit.co.kr, allan@forsit.co.kr, sungho@forsit.co.kr (고정)
- 첨부 없음

## 종료 코드

- `0`: Draft 생성 성공
- `1`: 오류
