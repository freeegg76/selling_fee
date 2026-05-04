"""
고객사 발송용 Gmail Draft 생성기.

SP_Get_Contact_Mail로 수신자 조회 후 Invoice / Revenue Report / Transaction Report 첨부.
OAuth 2.0으로 info@forsit.co.kr 계정 인증 (첫 실행 시 브라우저 승인 필요).

Usage:
  python create_gmail_draft.py --yyyymm 202504 --company_code ABC --company_name "홍길동상사"
"""
import argparse
import base64
import os
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pyodbc
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


ROOT = find_project_root()
load_dotenv(ROOT / ".env")

GMAIL_FROM = os.getenv("GMAIL_FROM", "info@forsit.co.kr")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
TOKEN_PATH = str(ROOT / "gmail_token.json")

SUBJECT_TEMPLATE = "[아마존_Invoice] {company_name} Selling Fee invoice {yyyymm}"
BODY_TEMPLATE = (
    "안녕하세요 폴싯 빌링팀입니다.\n\n"
    "판매수수료 {yyyymm} invoice를 송부드립니다.\n\n"
    "폴싯 빌링팀 드림"
)


def _get_gmail():
    client_secret = os.getenv("OAUTH_CLIENT_SECRET", str(ROOT / "oauth_client_secret.json"))
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _db_conn():
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    server = os.getenv("DB_SERVER", "")
    db = os.getenv("DB_DATABASE", "")
    uid = os.getenv("DB_USER", "")
    pwd = os.getenv("DB_PASSWORD", "")
    trust = os.getenv("DB_TRUST_SERVER_CERT", "no")
    if uid and pwd:
        cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};TrustServerCertificate={trust};"
    else:
        cs = f"DRIVER={{{driver}}};SERVER={server};DATABASE={db};Trusted_Connection=yes;TrustServerCertificate={trust};"
    return pyodbc.connect(cs, timeout=30)


def _get_contact_emails(company_code: str) -> tuple[list[str], list[str]]:
    """Returns (to_emails, cc_emails)."""
    conn = _db_conn()
    try:
        cur = conn.cursor()
        to_emails, cc_emails = [], []
        for mail_type in ("To", "CC"):
            cur.execute(
                "EXEC SP_Get_Contact_Mail @CompanyCode=?, @MailType=?",
                (company_code, mail_type),
            )
            if cur.description:
                cols = [c[0] for c in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                emails = [r["email"] for r in rows if r.get("email")]
                if mail_type == "To":
                    to_emails = emails
                else:
                    cc_emails = emails
        return to_emails, cc_emails
    finally:
        conn.close()


def _build_message(to_emails: list[str], subject: str, body: str,
                   attachment_paths: list[str], cc_emails: list[str] | None = None) -> str:
    msg = MIMEMultipart()
    msg["to"] = ", ".join(to_emails)
    msg["from"] = GMAIL_FROM
    msg["subject"] = subject
    if cc_emails:
        msg["cc"] = ", ".join(cc_emails)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachment_paths:
        p = Path(path)
        if not p.exists():
            print(f"WARN: 첨부 파일 없음: {path}", file=sys.stderr)
            continue
        with open(p, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{p.name}"')
        msg.attach(part)

    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yyyymm", required=True)
    parser.add_argument("--company_code", required=True)
    parser.add_argument("--company_name", required=True)
    parser.add_argument("--base_dir", default="output")
    args = parser.parse_args()

    base = Path(args.base_dir) / args.yyyymm / args.company_code
    attachments = [
        str(base / "invoice.pdf"),
        str(base / "revenue_report.pdf"),
        str(base / "transaction_report.xlsx"),
    ]

    # 수신자 조회
    to_emails, cc_emails = _get_contact_emails(args.company_code)
    if not to_emails:
        print(f"ERROR: 수신자 이메일 없음 (mail_type=To): {args.company_code}", file=sys.stderr)
        sys.exit(1)

    subject = SUBJECT_TEMPLATE.format(company_name=args.company_name, yyyymm=args.yyyymm)
    body = BODY_TEMPLATE.format(yyyymm=args.yyyymm)

    raw = _build_message(to_emails, subject, body, attachments, cc_emails)

    gmail = _get_gmail()
    draft = gmail.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()

    all_recipients = to_emails + cc_emails
    print(f"Gmail Draft 생성 완료: {draft['id']} → {', '.join(all_recipients)}")


if __name__ == "__main__":
    main()
