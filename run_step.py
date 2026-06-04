"""
Helper runner script to avoid PowerShell JSON quoting issues.
Usage: python run_step.py <sp_name> <params_json> <output_path>
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.claude', 'skills', 'db-caller', 'scripts'))

import json
import argparse
from pathlib import Path
from call_sp import call_sp

def main():
    sp_name = sys.argv[1]
    params = json.loads(sys.argv[2])
    output_path = sys.argv[3]

    result = call_sp(sp_name, params)
    output_str = json.dumps(result, ensure_ascii=False, indent=2)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_str, encoding="utf-8")
    print(f"저장 완료: {output_path} ({len(result)}건)")

if __name__ == "__main__":
    main()
