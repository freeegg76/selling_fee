# 판매수수료 자동화 에이전트 - 오케스트레이터

## 역할

아마존 판매수수료 월별 정산 프로세스를 자동화하는 오케스트레이터다.
사용자가 `YYYYMM` 형식의 정산 기간을 입력하면 전체 워크플로우를 실행한다.
설계 상세는 `selling-fee-agent-design.md` 참조.

## 실행 방법

사용자가 6자리 숫자(예: `202504`, `2025년 4월`, "4월 정산 실행" 등)를 입력하면 YYYYMM을 파악하고 아래 워크플로우를 시작한다.

---

## 사전 점검

YYYYMM을 확인한 뒤:

1. `.env` 파일 존재 확인. 없으면 `.env.template`을 복사하여 설정하도록 안내 후 중단.
2. `credential.json` 파일 존재 확인. 없으면 Google 서비스 계정 키 파일이 필요하다고 안내 후 중단.
3. `output/{YYYYMM}/` 디렉터리 존재 여부 확인:
   - **없으면**: 최초 실행. STEP 1로 이동.
   - **있으면**: 사용자에게 선택 요청:
     ```
     output/{YYYYMM}/ 에 기존 처리 내역이 있습니다.
     A. 실패 고객사만 재처리 (invoice.pdf 없는 고객사만)
     B. 전체 재처리 (모든 고객사 덮어쓰기)
     ```
     - A 선택: clients.json 로드 → invoice.pdf 없는 company_code만 처리 대상으로 설정
     - B 선택: 전체 재처리

---

## STEP 1: 처리 대상 고객사 조회

```bash
python .claude/skills/db-caller/scripts/call_sp.py --sp SP_Get_AmzOrder_By_Period --params "{\"@YYYYMM\": \"YYYYMM\"}" --output output/YYYYMM/clients_raw.json
```

결과에서 고유 (company_code, company_name) 목록을 추출하여 `output/{YYYYMM}/clients.json`에 저장:
```json
[{"company_code": "ABC", "company_name": "회사명"}]
```

고객사 목록이 비어 있으면: 에스컬레이션 Draft 생성 후 전체 중단.

---

## STEP 2: 고객사별 병렬 처리 시작

`clients.json`(또는 재처리 대상 목록)의 각 고객사에 대해 `client-processor` 서브에이전트를 **Task로 병렬 실행**한다.

각 Task 프롬프트 형식:
```
정산월: {YYYYMM}
고객사 코드: {company_code}
고객사명: {company_name}
```

- 개별 Task 실패는 해당 고객사만 FAILED 처리하고 나머지는 계속 진행한다.
- 고객사별 타임아웃: 30분.

---

## STEP 12: 전체 결과 집계

모든 Task 완료 후:

1. 각 Task 반환값에서 상태(SUCCESS / FAILED / PARTIAL) 수집.
2. 콘솔에 요약 출력:
   ```
   === 판매수수료 정산 완료 ({YYYYMM}) ===
   SUCCESS : N개사
   FAILED  : N개사 → {목록}
   PARTIAL : N개사 → {목록}
   ```
3. FAILED 고객사가 있으면 에스컬레이션 Draft가 각 고객사 처리 중 이미 생성되었음을 확인하고 확인 요청.

---

## 에스컬레이션 규칙

FAILED 고객사 발생 시 `client-processor`가 에스컬레이션 Draft를 생성하지만,
오케스트레이터가 전체 처리 후 누락된 에스컬레이션이 없는지 확인한다.

---

## 스킬 참조

| 스킬 | 경로 |
|------|------|
| db-caller | `.claude/skills/db-caller/SKILL.md` |
| report-generator | `.claude/skills/report-generator/SKILL.md` |
| drive-uploader | `.claude/skills/drive-uploader/SKILL.md` |
| gmail-drafter | `.claude/skills/gmail-drafter/SKILL.md` |
| process-logger | `.claude/skills/process-logger/SKILL.md` |
