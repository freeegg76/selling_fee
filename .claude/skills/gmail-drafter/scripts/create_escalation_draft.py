"""
에스컬레이션용 Gmail Draft 생성기.

FAILED 고객사 발생 시 내부 담당자에게 처리 중단 사유와 필요 조치를 Draft로 전달.
info@forsit.co.kr 계정으로 impersonate.

Usage:
  python create_escalation_draft.py \
    --yyyymm 202504 \
    --company_code ABC \
    --company_name "홍길동상사" \
    --step "STEP 7 - 익월 환율 조회" \
    --message "환율 데이터 없음: KRW 2025-05-01 이후 데이터 없음"
"""
import argparse
import base64
import os
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build


def find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


ROOT = find_project_root()
load_dotenv(ROOT / ".env")

GMAIL_FROM = os.getenv("GMAIL_FROM", "info@forsit.co.kr")
CREDENTIALS_FILE = str(ROOT / os.getenv("GOOGLE_CREDENTIALS_FILE", "credential.json"))
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

ESCALATION_RECIPIENTS = [
    e.strip()
    for e in os.getenv(
        "ESCALATION_RECIPIENTS",
        "dayeon@forsit.co.kr,allan@forsit.co.kr,sungho@forsit.co.kr",
    ).split(",")
    if e.strip()
]


def _get_gmail():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=GMAIL_SCOPES
    )
    return build("gmail", "v1", credentials=creds.with_subject(GMAIL_FROM))


def _build_body(company_code: str, company_name: str, yyyymm: str,
                step: str, message: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"[판매수수료 정산 처리 오류 알림]\n\n"
        f"정산월      : {yyyymm}\n"
        f"고객사 코드 : {company_code}\n"
        f"고객사명    : {company_name}\n"
        f"실패 단계   : {step}\n"
        f"오류 내용   : {message}\n"
        f"발생 시각   : {ts}\n\n"
        f"[필요 조치]\n"
        f"위 오류를 확인하고 수동으로 해당 고객사 데이터를 점검해 주세요.\n"
        f"조치 완료 후 해당 고객사만 재처리하거나 전체 재실행 여부를 결정해 주세요.\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yyyymm", required=True)
    parser.add_argument("--company_code", required=True)
    parser.add_argument("--company_name", required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()

    subject = f"[에스컬레이션] {args.company_name} 판매수수료 정산 오류 - {args.yyyymm} / {args.step}"
    body = _build_body(
        args.company_code, args.company_name,
        args.yyyymm, args.step, args.message,
    )

    msg = MIMEMultipart()
    msg["to"] = ", ".join(ESCALATION_RECIPIENTS)
    msg["from"] = GMAIL_FROM
    msg["subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        gmail = _get_gmail()
        draft = gmail.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        print(f"에스컬레이션 Draft 생성 완료: {draft['id']} → {', '.join(ESCALATION_RECIPIENTS)}")
    except Exception as e:
        print(f"ERROR: 에스컬레이션 Draft 생성 실패: {e}", file=sys.stderr)
        print(f"[콘솔 에스컬레이션] {args.company_name} / {args.step} / {args.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
