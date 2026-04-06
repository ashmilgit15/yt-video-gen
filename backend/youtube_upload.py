import os
import random
import time
from datetime import datetime, timezone

import requests
from google.auth.transport.requests import Request as GoogleRequest

from config import settings
from youtube_oauth import build_google_credentials, encrypt_token


YOUTUBE_RESUMABLE_UPLOAD_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
REQUEST_TIMEOUT = (15, 300)


class RetryableUploadError(RuntimeError):
    def __init__(self, message: str, session_uri: str | None = None):
        super().__init__(message)
        self.session_uri = session_uri


class PermanentUploadError(RuntimeError):
    def __init__(self, message: str, session_uri: str | None = None):
        super().__init__(message)
        self.session_uri = session_uri


def _serialize_credentials(credentials) -> dict:
    expiry = credentials.expiry
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    return {
        "access_token_encrypted": encrypt_token(credentials.token),
        "refresh_token_encrypted": encrypt_token(credentials.refresh_token),
        "token_expires_at": expiry,
        "scopes_json": list(credentials.scopes or settings.google_oauth_scopes),
    }


def _format_publish_at(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_upload_body(metadata: dict) -> dict:
    publish_at = _format_publish_at(metadata.get("publish_at"))
    privacy_status = metadata.get("privacy_status") or "private"

    status = {
        "privacyStatus": "private" if publish_at else privacy_status,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }
    if publish_at:
        status["publishAt"] = publish_at

    return {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata.get("tags") or None,
            "categoryId": metadata.get("category_id") or "22",
        },
        "status": status,
    }


def _sleep_for_retry(attempt: int) -> None:
    time.sleep(random.uniform(1.0, 2.0**attempt))


def _refresh_credentials(account):
    expiry = getattr(account, "token_expires_at", None)
    if expiry is not None:
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        else:
            expiry = expiry.astimezone(timezone.utc)
        account.token_expires_at = expiry

    credentials = build_google_credentials(account)
    if credentials.expiry is not None:
        if credentials.expiry.tzinfo is None:
            credentials.expiry = credentials.expiry.replace(tzinfo=timezone.utc)
        else:
            credentials.expiry = credentials.expiry.astimezone(timezone.utc)

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleRequest())
    return credentials


def _start_resumable_session(
    access_token: str,
    file_size: int,
    content_type: str,
    metadata: dict,
) -> str:
    response = requests.post(
        YOUTUBE_RESUMABLE_UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": content_type,
        },
        json=build_upload_body(metadata),
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code in RETRIABLE_STATUS_CODES:
        raise RetryableUploadError(
            f"YouTube rejected resumable session startup with {response.status_code}."
        )
    if response.status_code == 401:
        raise RetryableUploadError("Google access token expired while starting upload.")
    if response.status_code >= 400:
        raise PermanentUploadError(
            f"Failed to start resumable upload: {response.status_code} {response.text}"
        )

    session_uri = response.headers.get("Location")
    if not session_uri:
        raise PermanentUploadError(
            "YouTube did not return a resumable upload session URI."
        )
    return session_uri


def _query_upload_status(access_token: str, session_uri: str, file_size: int) -> dict:
    response = requests.put(
        session_uri,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Length": "0",
            "Content-Range": f"bytes */{file_size}",
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code in (200, 201):
        return {"completed": True, "response": response.json()}
    if response.status_code == 308:
        upload_range = response.headers.get("Range")
        if not upload_range:
            return {"completed": False, "next_byte": 0}
        uploaded_end = int(upload_range.split("-")[1])
        return {"completed": False, "next_byte": uploaded_end + 1}
    if response.status_code == 404:
        return {"completed": False, "expired": True}
    if response.status_code == 401:
        raise RetryableUploadError(
            "Google access token expired while checking upload status.", session_uri
        )
    if response.status_code in RETRIABLE_STATUS_CODES:
        raise RetryableUploadError(
            f"YouTube upload status check failed with {response.status_code}.",
            session_uri,
        )
    raise PermanentUploadError(
        f"YouTube upload status check failed: {response.status_code} {response.text}",
        session_uri,
    )


def _send_remaining_bytes(
    access_token: str,
    session_uri: str,
    file_path: str,
    start_byte: int,
    file_size: int,
    content_type: str,
):
    with open(file_path, "rb") as file_handle:
        file_handle.seek(start_byte)
        response = requests.put(
            session_uri,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Length": str(file_size - start_byte),
                "Content-Type": content_type,
                "Content-Range": f"bytes {start_byte}-{file_size - 1}/{file_size}",
            },
            data=file_handle,
            timeout=REQUEST_TIMEOUT,
        )

    if response.status_code in (200, 201):
        return {"completed": True, "response": response.json()}
    if response.status_code == 308:
        upload_range = response.headers.get("Range")
        next_byte = 0 if not upload_range else int(upload_range.split("-")[1]) + 1
        return {"completed": False, "next_byte": next_byte}
    if response.status_code == 404:
        return {"completed": False, "expired": True}
    if response.status_code == 401:
        raise RetryableUploadError(
            "Google access token expired while uploading bytes.", session_uri
        )
    if response.status_code in RETRIABLE_STATUS_CODES:
        raise RetryableUploadError(
            f"YouTube returned {response.status_code} during resumable upload.",
            session_uri,
        )
    raise PermanentUploadError(
        f"YouTube upload failed: {response.status_code} {response.text}",
        session_uri,
    )


def upload_video_to_youtube(
    video_path: str,
    account,
    metadata: dict,
    session_uri: str | None = None,
) -> dict:
    file_size = os.path.getsize(video_path)
    content_type = "video/mp4"
    credentials = _refresh_credentials(account)
    access_token = credentials.token
    current_session_uri = session_uri
    transient_attempts = 0

    while True:
        try:
            if not current_session_uri:
                current_session_uri = _start_resumable_session(
                    access_token, file_size, content_type, metadata
                )

            status = _query_upload_status(access_token, current_session_uri, file_size)
            if status.get("expired"):
                current_session_uri = _start_resumable_session(
                    access_token, file_size, content_type, metadata
                )
                status = {"completed": False, "next_byte": 0}

            if status.get("completed"):
                response = status["response"]
            else:
                response = None
                while response is None:
                    upload_state = _send_remaining_bytes(
                        access_token,
                        current_session_uri,
                        video_path,
                        status.get("next_byte", 0),
                        file_size,
                        content_type,
                    )
                    if upload_state.get("expired"):
                        current_session_uri = _start_resumable_session(
                            access_token, file_size, content_type, metadata
                        )
                        status = {"completed": False, "next_byte": 0}
                        continue
                    if upload_state.get("completed"):
                        response = upload_state["response"]
                    else:
                        status = upload_state

            if not response or "id" not in response:
                raise PermanentUploadError(
                    f"Unexpected YouTube upload response: {response}",
                    current_session_uri,
                )

            return {
                "youtube_video_id": response["id"],
                "youtube_url": f"https://www.youtube.com/watch?v={response['id']}",
                "credentials": _serialize_credentials(credentials),
            }
        except RetryableUploadError as exc:
            transient_attempts += 1
            if transient_attempts >= 5:
                raise RetryableUploadError(
                    str(exc), exc.session_uri or current_session_uri
                )

            current_session_uri = exc.session_uri or current_session_uri
            if "expired" in str(exc).lower():
                current_session_uri = None

            credentials = _refresh_credentials(account)
            access_token = credentials.token
            _sleep_for_retry(transient_attempts)
        except requests.RequestException as exc:
            transient_attempts += 1
            if transient_attempts >= 5:
                raise RetryableUploadError(
                    f"Network error during YouTube upload: {exc}", current_session_uri
                )
            _sleep_for_retry(transient_attempts)
