# process-logger 스킬

## 역할

각 처리 단계의 성공/실패 결과를 DB에 기록한다 (SP_Insert_Processing_Log 호출).

## 사용법

```bash
python .claude/skills/process-logger/scripts/insert_log.py \
  --yyyymm 202504 \
  --company_code ABC \
  --step "STEP 3 - 주문 조회" \
  --status SUCCESS \
  --message "주문 123건 처리 완료"
```

## 파라미터

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--yyyymm` | 필수 | 정산월 |
| `--company_code` | 필수 | 고객사 코드 |
| `--step` | 필수 | 단계명 |
| `--status` | 필수 | SUCCESS / FAILED / PARTIAL / SKIPPED |
| `--message` | 선택 | 상세 메시지 |

## 종료 코드

- `0`: 저장 성공
- `1`: 저장 실패 (전체 흐름을 막지 않음 — 스킵 처리)
