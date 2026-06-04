"""지정 고객사만 재처리."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# run_202605.py의 run_client 함수 재사용
import run_202605

targets = [
    {"company_code": "1004",  "company_name": "주식회사 제네웰"},
    {"company_code": "00970", "company_name": "ABLE C&C US INC"},
]

results = {}
for c in targets:
    try:
        result = run_202605.run_client(c["company_code"], c["company_name"])
        results[c["company_code"]] = {"name": c["company_name"], "status": result}
    except Exception as e:
        results[c["company_code"]] = {"name": c["company_name"], "status": f"FAILED: {e}"}
        print(f"\n[EXCEPTION] {c['company_name']}: {e}")

print(f"\n{'='*60}")
print("=== 재처리 완료 ===")
for cc, v in results.items():
    print(f"  {cc} {v['name']}: {v['status']}")
