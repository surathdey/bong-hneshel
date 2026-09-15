"""
Google Drive integration (service-account based).

Credentials are loaded from the ENCRYPTED service-account JSON stored in
MongoDB `business_settings.google_drive.service_account_json_encrypted`.

Public API:
    async test_folder(encrypted_json, folder_id) -> dict
    async upload_xlsx(encrypted_json, folder_id, user_email, filename, data) -> dict
        returns {"id", "name", "web_view_link"}

All errors bubble up as `DriveError(status, message)` — the API layer maps
those into HTTPException.
"""
from __future__ import annotations

import asyncio
import json
from io import BytesIO
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from settings_crypto import decrypt_service_account_json

SCOPES = ["https://www.googleapis.com/auth/drive"]
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class DriveError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def _reason(err: HttpError) -> str:
    try:
        return json.loads(err.content.decode()).get("error", {}) \
            .get("errors", [{}])[0].get("reason", "")
    except Exception:
        return ""


def _map_error(err: HttpError) -> DriveError:
    status = int(err.resp.status)
    reason = _reason(err)
    if status == 401:
        return DriveError(401, "Invalid or expired Google credentials — check the service-account JSON.")
    if status == 403:
        return DriveError(
            403,
            "Google Drive denied access — make sure the folder is SHARED with the "
            f"service account email (as Editor). Reason: {reason or 'forbidden'}."
        )
    if status == 404:
        return DriveError(404, "Drive folder not found. Double-check the folder ID.")
    return DriveError(status, f"Google Drive error: {reason or err}")


def _build_drive(encrypted_json: str):
    try:
        info = decrypt_service_account_json(encrypted_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except DriveError:
        raise
    except Exception as e:
        # Bad JSON, malformed / fake private key, decrypt failure, etc.
        raise DriveError(400, f"Invalid Google service-account credentials: {e}")


def _test_folder_sync(encrypted_json: str, folder_id: str) -> dict:
    try:
        drive = _build_drive(encrypted_json)
        return drive.files().get(
            fileId=folder_id,
            fields="id,name,mimeType,capabilities(canAddChildren)",
            supportsAllDrives=True,
        ).execute()
    except DriveError:
        raise
    except HttpError as e:
        raise _map_error(e) from e
    except Exception as e:
        raise DriveError(400, f"Google Drive request failed: {e}")


def _upload_sync(encrypted_json: str, folder_id: str, user_email: str | None,
                 filename: str, data: bytes) -> dict[str, Any]:
    try:
        drive = _build_drive(encrypted_json)
        metadata = {"name": filename, "parents": [folder_id], "mimeType": XLSX_MIME}
        stream = BytesIO(data)
        stream.seek(0)
        media = MediaIoBaseUpload(stream, mimetype=XLSX_MIME, resumable=True)
        created = drive.files().create(
            body=metadata, media_body=media,
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        ).execute()
        file_id = created["id"]

        # Anyone with the link → viewer.
        try:
            drive.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id", supportsAllDrives=True,
            ).execute()
        except HttpError as e:
            # Workspace policy may block "anyone" sharing; not fatal.
            pass

        # Explicitly share back with the user's email so it shows in their Drive.
        if user_email:
            try:
                drive.permissions().create(
                    fileId=file_id,
                    body={"type": "user", "role": "reader", "emailAddress": user_email},
                    sendNotificationEmail=False,
                    fields="id", supportsAllDrives=True,
                ).execute()
            except HttpError:
                pass

        final = drive.files().get(
            fileId=file_id, fields="id,name,webViewLink",
            supportsAllDrives=True,
        ).execute()
        return {
            "id": final["id"],
            "name": final["name"],
            "web_view_link": final.get("webViewLink", ""),
        }
    except DriveError:
        raise


# -------------------------------------------------------------------- async ---
    except HttpError as e:
        raise _map_error(e) from e
    except Exception as e:
        raise DriveError(400, f"Google Drive upload failed: {e}")
async def test_folder(encrypted_json: str, folder_id: str) -> dict:
    return await asyncio.to_thread(_test_folder_sync, encrypted_json, folder_id)


async def upload_xlsx(encrypted_json: str, folder_id: str,
                      user_email: str | None, filename: str,
                      data: bytes) -> dict:
    return await asyncio.to_thread(
        _upload_sync, encrypted_json, folder_id, user_email, filename, data
    )
