import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    database_url: str | None = os.getenv("DATABASE_URL")
    clerk_secret_key: str | None = os.getenv("CLERK_SECRET_KEY")
    google_client_id: str | None = os.getenv("GOOGLE_CLIENT_ID")
    google_client_secret: str | None = os.getenv("GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/youtube/connect/callback"
    )
    google_token_encryption_key: str | None = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local").lower()
    storage_local_dir: str = os.getenv(
        "STORAGE_LOCAL_DIR", os.path.join(os.path.dirname(__file__), "storage")
    )
    storage_s3_bucket: str | None = os.getenv("STORAGE_S3_BUCKET")
    storage_s3_region: str | None = os.getenv("STORAGE_S3_REGION")
    storage_s3_endpoint_url: str | None = os.getenv("STORAGE_S3_ENDPOINT_URL")
    storage_s3_access_key_id: str | None = os.getenv("STORAGE_S3_ACCESS_KEY_ID")
    storage_s3_secret_access_key: str | None = os.getenv("STORAGE_S3_SECRET_ACCESS_KEY")
    storage_s3_prefix: str = os.getenv("STORAGE_S3_PREFIX", "")
    upload_retry_base_seconds: int = _env_int("UPLOAD_RETRY_BASE_SECONDS", 30)
    upload_retry_max_seconds: int = _env_int("UPLOAD_RETRY_MAX_SECONDS", 900)
    upload_retry_default_attempts: int = _env_int("UPLOAD_RETRY_DEFAULT_ATTEMPTS", 3)
    image_generation_timeout_seconds: int = _env_int(
        "IMAGE_GENERATION_TIMEOUT_SECONDS", 35
    )
    image_generation_connect_timeout_seconds: int = _env_int(
        "IMAGE_GENERATION_CONNECT_TIMEOUT_SECONDS", 10
    )
    image_generation_max_retries: int = _env_int("IMAGE_GENERATION_MAX_RETRIES", 2)
    scene_concurrency: int = max(1, _env_int("SCENE_CONCURRENCY", 2))
    pollinations_min_interval_seconds: int = _env_int(
        "POLLINATIONS_MIN_INTERVAL_SECONDS", 5
    )
    pollinations_referrer: str = os.getenv("POLLINATIONS_REFERRER", "localhost")
    pollinations_model: str = os.getenv("POLLINATIONS_MODEL", "flux")
    image_generation_width: int = _env_int("IMAGE_GENERATION_WIDTH", 1024)
    image_generation_height: int = _env_int("IMAGE_GENERATION_HEIGHT", 1792)

    @property
    def cors_origins(self) -> list[str]:
        origins = _split_csv(os.getenv("CORS_ORIGINS"))
        return origins or [self.frontend_url]

    @property
    def clerk_authorized_parties(self) -> list[str]:
        parties = _split_csv(os.getenv("CLERK_AUTHORIZED_PARTIES"))
        return parties or [self.frontend_url]

    @property
    def google_oauth_scopes(self) -> list[str]:
        return [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
        ]

    @property
    def google_client_config(self) -> dict | None:
        if not self.google_client_id or not self.google_client_secret:
            return None

        return {
            "web": {
                "client_id": self.google_client_id,
                "client_secret": self.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.google_redirect_uri],
            }
        }

    @property
    def is_s3_storage(self) -> bool:
        return self.storage_backend == "s3"

    @property
    def frontend_host(self) -> str:
        parsed = urlparse(self.frontend_url)
        return parsed.netloc or parsed.path or "localhost"


settings = Settings()
