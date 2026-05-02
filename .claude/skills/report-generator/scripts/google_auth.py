"""
Google API 인증 공통 모듈.
서비스 계정 credential.json으로 Sheets / Drive / Gmail 서비스를 생성한다.
"""
import os
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

SCOPES_DRIVE_SHEETS = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
SCOPES_GMAIL = [
    "https://www.googleapis.com/auth/gmail.compose",
]


def _credentials_path() -> str:
    cred_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credential.json")
    path = ROOT / cred_file
    if not path.exists():
        raise FileNotFoundError(f"credential.json not found: {path}")
    return str(path)


def get_sheets_and_drive():
    creds = service_account.Credentials.from_service_account_file(
        _credentials_path(), scopes=SCOPES_DRIVE_SHEETS
    )
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return sheets, drive


def get_gmail(impersonate_as: str):
    creds = service_account.Credentials.from_service_account_file(
        _credentials_path(), scopes=SCOPES_GMAIL
    )
    delegated = creds.with_subject(impersonate_as)
    return build("gmail", "v1", credentials=delegated)
