# report-generator 스킬

## 역할

Google Sheets 템플릿을 이용하여 Invoice(PDF), Transaction Report(xlsx), Revenue Report(PDF)를 생성한다.

**생성 방식**:
1. 템플릿 스프레드시트를 임시 복사
2. 해당 탭만 남기고 나머지 삭제
3. Sheets API `findReplace`로 플레이스홀더 치환 및 데이터 범위 삽입
4. Drive API `export`로 PDF/xlsx 다운로드
5. 임시 스프레드시트 삭제

## 사용법

### Invoice PDF

```bash
python .claude/skills/report-generator/scripts/generate_invoice_pdf.py \
  --yyyymm 202504 --company_code ABC --base_dir output
```

출력: `output/202504/ABC/invoice.pdf`

### Transaction Report (xlsx)

```bash
python .claude/skills/report-generator/scripts/generate_transaction_xlsx.py \
  --yyyymm 202504 --company_code ABC --base_dir output
```

출력: `output/202504/ABC/transaction_report.xlsx`

### Revenue Report PDF

```bash
python .claude/skills/report-generator/scripts/generate_revenue_pdf.py \
  --yyyymm 202504 --company_code ABC --base_dir output
```

출력: `output/202504/ABC/revenue_report.pdf`

## 사전 조건

- `credential.json`: 프로젝트 루트에 위치 (Drive + Sheets 접근 권한)
- 템플릿 스프레드시트 ID: `.env`의 `TEMPLATE_SPREADSHEET_ID`
- 각 스크립트 실행 전 해당 STEP의 JSON 파일이 생성되어 있어야 함

## 종료 코드

- `0`: 성공
- `1`: 오류 (스프레드시트 조작 실패, 내보내기 실패 등)
