"""Helper script to run SP calls without shell escaping issues."""
import sys
import subprocess
import json
import os

def run_sp(sp_name, params_dict, output_path):
    params_json = json.dumps(params_dict)
    result = subprocess.run(
        [
            r"c:\Dev\SellingFee\.venv\Scripts\python.exe",
            r"c:\Dev\SellingFee\.claude\skills\db-caller\scripts\call_sp.py",
            "--sp", sp_name,
            "--params", params_json,
            "--output", output_path
        ],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sp", required=True)
    parser.add_argument("--params", required=True)  # JSON string
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    params = json.loads(args.params)
    rc = run_sp(args.sp, params, args.output)
    sys.exit(rc)
