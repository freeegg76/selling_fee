"""SP 수정 결과 검증: MXN(1004), BRL(00970) 주문의 *USD 필드 확인."""
import sys, os
from pathlib import Path
ROOT = Path(r"c:\Dev\SellingFee")
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "db-caller" / "scripts"))
os.chdir(ROOT)
from call_sp import call_sp
import json

for cc, label in [("1004", "제네웰(MXN)"), ("00970", "ABLE C&C(BRL)")]:
    rows = call_sp("SP_Convert_Order_Amount_To_USD", {"@YYYYMM": "202605", "@CompanyCode": cc})
    non_usd = [r for r in rows if r.get("Currency") and r["Currency"] != "USD"]
    print(f"\n=== {label} - 비USD 주문 (처음 3건) ===")
    for r in non_usd[:3]:
        print(f"  Currency={r['Currency']}, RateToUSD={r['RateToUSD']}, "
              f"ItemPrice={r['ItemPrice']}, ItemPriceUSD={r['ItemPriceUSD']}")
