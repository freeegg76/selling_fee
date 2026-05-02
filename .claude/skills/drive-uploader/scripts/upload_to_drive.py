"""
Google Drive 업로드.

루트/{YYYYMM}/ 폴더에 3개 파일 업로드.
오류 시 루트/Error/ 폴더에 저장 + 에러 로그 생성.

Usage:
  python upload_to_drive.py --yyyymm 202504 --company_code ABC --company_name "홍길동상사"
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def find_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    return Path.cwd()


ROOT = find_project_root()
load_dotenv(ROOT / ".env")

ROOT_FOLDER_ID = os.getenv("DRIVE_ROOT_FOLDER_ID", "15_PI1CkFgwz6l6vbr_qauGcgBRy_scLb")
CREDENTIALS_FILE = str(ROOT / os.getenv("GOOGLE_CREDENTIALS_FILE", "credential.json"))
SCOPES = ["https://www.googleapis.com/auth/drive"]

MIME_MAP = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
FOLDER_MIME = "application/vnd.google-apps.folder"


def _get_drive():
    creds = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def _find_folder(drive, parent_id: str, name: str) -> str | None:
    q = f"name='{name}' and '{parent_id}' in parents and mimeType='{FOLDER_MIME}' and trashed=false"
    res = drive.files().list(q=q, fields="files(id)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(drive, parent_id: str, name: str) -> str:
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]}
    f = drive.files().create(body=meta, fields="id").execute()
    return f["id"]


def _find_or_create_folder(drive, parent_id: str, name: str) -> str:
    folder_id = _find_folder(drive, parent_id, name)
    if not folder_id:
        folder_id = _create_folder(drive, parent_id, name)
        print(f"폴더 생성: {name}")
    return folder_id


def _upload_file(drive, folder_id: str, local_path: str, drive_name: str):
    ext = Path(local_path).suffix.lower()
    mime = MIME_MAP.get(ext, "application/octet-stream")

    # 기존 파일 확인
    q = f"name='{drive_name}' and '{folder_id}' in parents and trashed=false"
    res = drive.files().list(q=q, fields="files(id)").execute()
    existing = res.get("files", [])

    media = MediaFileUpload(local_path, mimetype=mime)
    if existing:
        drive.files().update(fileId=existing[0]["id"], media_body=media).execute()
        print(f"  덮어쓰기: {drive_name}")
    else:
        meta = {"name": drive_name, "parents": [folder_id]}
        drive.files().create(body=meta, media_body=media, fields="id").execute()
        print(f"  업로드: {drive_name}")


def _write_error_log(drive, error_folder_id: str, company_code: str, company_name: str,
                     yyyymm: str, error_step: str, error_message: str):
    log_content = (
        f"company_code  : {company_code}\n"
        f"company_name  : {company_name}\n"
        f"period        : {yyyymm}\n"
        f"error_step    : {error_step}\n"
        f"error_message : {error_message}\n"
        f"timestamp     : {datetime.now(timezone.utc).isoformat()}\n"
    )
    log_path = ROOT / f"_temp_{company_code}_error.log"
    log_path.write_text(log_content, encoding="utf-8")

    media = MediaFileUpload(str(log_path), mimetype="text/plain")
    log_name = f"{company_code}_error.log"
    q = f"name='{log_name}' and '{error_folder_id}' in parents and trashed=false"
    existing = drive.files().list(q=q, fields="files(id)").execute().get("files", [])
    if existing:
        drive.files().update(fileId=existing[0]["id"], media_body=media).execute()
    else:
        drive.files().create(
            body={"name": log_name, "parents": [error_folder_id]},
            media_body=media, fields="id"
        ).execute()

    log_path.unlink(missing_ok=True)
    print(f"  에러 로그 저장: {log_name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--yyyymm", required=True)
    parser.add_argument("--company_code", required=True)
    parser.add_argument("--company_name", required=True)
    parser.add_argument("--base_dir", default="output")
    args = parser.parse_args()

    cc = args.company_code
    yyyymm = args.yyyymm
    base = Path(args.base_dir) / yyyymm / cc

    files_to_upload = [
        (str(base / "revenue_report.pdf"), f"Revenue_Report_{cc}_{yyyymm}.pdf"),
        (str(base / "transaction_report.xlsx"), f"Transaction_Report_{cc}_{yyyymm}.xlsx"),
        (str(base / "invoice.pdf"), f"Invoice_{cc}_{yyyymm}.pdf"),
    ]

    # 파일 존재 확인
    for local_path, _ in files_to_upload:
        if not Path(local_path).exists():
            print(f"ERROR: 파일 없음: {local_path}", file=sys.stderr)
            sys.exit(1)

    drive = _get_drive()

    try:
        period_folder_id = _find_or_create_folder(drive, ROOT_FOLDER_ID, yyyymm)
        for local_path, drive_name in files_to_upload:
            _upload_file(drive, period_folder_id, local_path, drive_name)
        print(f"Drive 업로드 완료: {cc} ({yyyymm})")

    except Exception as e:
        print(f"ERROR: Drive 업로드 실패: {e}", file=sys.stderr)
        print("Error 폴더로 전환합니다...")
        try:
            error_folder_id = _find_or_create_folder(drive, ROOT_FOLDER_ID, "Error")
            for local_path, drive_name in files_to_upload:
                if Path(local_path).exists():
                    _upload_file(drive, error_folder_id, local_path, drive_name)
            _write_error_log(
                drive, error_folder_id,
                cc, args.company_name, yyyymm,
                "STEP 9 - Google Drive Upload", str(e)
            )
        except Exception as e2:
            print(f"ERROR: Error 폴더 저장도 실패: {e2}", file=sys.stderr)
            sys.exit(1)

        # Error 폴더에는 저장됐으므로 에스컬레이션은 호출자(agent)가 처리
        print(f"Error 폴더에 저장 완료: {cc}")
        sys.exit(2)  # 2 = Error 폴더 저장됨 (에스컬레이션 필요)


if __name__ == "__main__":
    main()
