# drive-uploader 스킬

## 역할

산출물 3개 파일을 Google Drive의 지정 폴더에 업로드한다.

- 루트 폴더 ID: `.env`의 `DRIVE_ROOT_FOLDER_ID`
- 폴더 구조: `{루트}/{YYYYMM}/`
- YYYYMM 폴더 없으면 자동 생성
- 기존 파일은 덮어쓰기
- 업로드 실패 시: `{루트}/Error/` 폴더에 저장 + 에러 로그 생성

## 사용법

```bash
python .claude/skills/drive-uploader/scripts/upload_to_drive.py \
  --yyyymm 202504 \
  --company_code ABC \
  --company_name "홍길동상사" \
  [--base_dir output]
```

## 파일명 규칙 (Drive 업로드)

| 산출물 | Drive 파일명 |
|--------|-------------|
| revenue_report.pdf | `Revenue_Report_{CC}_{YYYYMM}.pdf` |
| transaction_report.xlsx | `Transaction_Report_{CC}_{YYYYMM}.xlsx` |
| invoice.pdf | `Invoice_{CC}_{YYYYMM}.pdf` |

## 종료 코드

- `0`: 성공 (정상 폴더 또는 Error 폴더 저장 포함)
- `1`: 치명적 오류 (Drive 연결 불가 등)
