# db-caller 스킬

## 역할

MS SQL Server의 저장 프로시저(SP)를 호출하고 결과를 JSON 파일로 저장한다.
모든 DB 접근은 이 스킬을 통해서만 수행한다.

## 사용법

```bash
python .claude/skills/db-caller/scripts/call_sp.py \
  --sp SP_NAME \
  --params '{"@PARAM1": "value1", "@PARAM2": "value2"}' \
  [--output path/to/output.json]
```

## 파라미터

| 옵션 | 필수 | 설명 |
|------|------|------|
| `--sp` | 필수 | 저장 프로시저 이름 |
| `--params` | 선택 | JSON 형식 파라미터 (기본값: `{}`) |
| `--output` | 선택 | 결과를 저장할 파일 경로. 생략 시 stdout 출력 |

## 출력 형식

SP 결과셋을 JSON 배열로 반환:
```json
[
  {"column1": "value1", "column2": "value2"},
  ...
]
```

결과가 없으면 빈 배열 `[]` 반환.

## 종료 코드

- `0`: 성공
- `1`: 오류 (연결 실패, SP 실행 오류 등) — 오류 내용은 stderr 출력

## 사용 예시

```bash
# 기간별 주문 조회
python .claude/skills/db-caller/scripts/call_sp.py \
  --sp SP_Get_AmzOrder_By_Period \
  --params '{"@YYYYMM": "202504"}' \
  --output output/202504/clients_raw.json

# 고객사 주문 USD 환산
python .claude/skills/db-caller/scripts/call_sp.py \
  --sp SP_Convert_Order_Amount_To_USD \
  --params '{"@YYYYMM": "202504", "@CompanyCode": "ABC"}' \
  --output output/202504/ABC/orders_usd.json

# 셀링피 계산
python .claude/skills/db-caller/scripts/call_sp.py \
  --sp SP_Calc_Tiered_Selling_Fee \
  --params '{"@ContractNumber": "CN-001", "@PerformanceUSD": 123456.78}' \
  --output output/202504/ABC/selling_fee.json
```
