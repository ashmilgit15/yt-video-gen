from datetime import timezone

from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow

from config import settings


def _get_cipher() -> Fernet:
    if not settings.google_token_encryption_key:
        raise RuntimeError(
            "GOOGLE_TOKEN_ENCRYPTION_KEY is not configured. Generate a Fernet key and add it to backend/.env."
        )
    return Fernet(settings.google_token_encryption_key.encode("utf-8"))


def encrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    return _get_cipher().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_token(value: str | None) -> str | None:
    if not value:
        return None
    return _get_cipher().decrypt(value.encode("utf-8")).decode("utf-8")


def _build_flow(state: str | None = None) -> Flow:
    client_config = settings.google_client_config
    if client_config is None:
        raise RuntimeError(
            "Google OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env."
        )

    flow = Flow.from_client_config(
        client_config, scopes=settings.google_oauth_scopes, state=state
    )
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def build_google_auth_url(state: str) -> str:
    flow = _build_flow(state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent select_account",
    )
    return auth_url


def exchange_code_for_account(code: str, state: str) -> dict:
    flow = _build_flow(state)
    flow.fetch_token(code=code)
    credentials = flow.credentials

    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    channel_response = (
        youtube.channels().list(part="id,snippet", mine=True, maxResults=1).execute()
    )
    items = channel_response.get("items") or []
    if not items:
        raise RuntimeError(
            "No YouTube channel was found for the selected Google account."
        )

    channel = items[0]
    snippet = channel.get("snippet") or {}
    thumbnails = snippet.get("thumbnails") or {}
    thumbnail = (
        thumbnails.get("high")
        or thumbnails.get("medium")
        or thumbnails.get("default")
        or {}
    )

    expiry = credentials.expiry
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    return {
        "channel_id": channel.get("id"),
        "channel_title": snippet.get("title") or "YouTube Channel",
        "thumbnail_url": thumbnail.get("url"),
        "access_token_encrypted": encrypt_token(credentials.token),
        "refresh_token_encrypted": encrypt_token(credentials.refresh_token),
        "token_expires_at": expiry,
        "scopes_json": list(credentials.scopes or settings.google_oauth_scopes),
    }


def build_google_credentials(account) -> Credentials:
    credentials = Credentials(
        token=decrypt_token(account.access_token_encrypted),
        refresh_token=decrypt_token(account.refresh_token_encrypted),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=account.scopes_json or settings.google_oauth_scopes,
    )

    if account.token_expires_at is not None:
        credentials.expiry = account.token_expires_at

    return credentials
