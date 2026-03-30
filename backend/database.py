from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(database_url: str | None) -> str | None:
    if not database_url:
        return None
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


engine = (
    create_engine(
        _normalize_database_url(settings.database_url), pool_pre_ping=True, future=True
    )
    if settings.database_url
    else None
)

SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    if engine is not None
    else None
)


def require_database() -> None:
    if engine is None or SessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. Add it to backend/.env before starting the API."
        )


def init_db() -> None:
    require_database()
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE videos ADD COLUMN IF NOT EXISTS storage_provider VARCHAR(32)"
            )
        )
        connection.execute(
            text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS storage_key TEXT")
        )
        connection.execute(
            text(
                "ALTER TABLE videos ADD COLUMN IF NOT EXISTS output_filename VARCHAR(255)"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE videos ADD COLUMN IF NOT EXISTS output_mime_type VARCHAR(100)"
            )
        )
        connection.execute(
            text("ALTER TABLE uploads ADD COLUMN IF NOT EXISTS publish_at TIMESTAMPTZ")
        )
        connection.execute(
            text("ALTER TABLE uploads ADD COLUMN IF NOT EXISTS retry_count INTEGER")
        )
        connection.execute(
            text("ALTER TABLE uploads ADD COLUMN IF NOT EXISTS max_retries INTEGER")
        )
        connection.execute(
            text(
                "ALTER TABLE uploads ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE uploads ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ"
            )
        )
        connection.execute(
            text("ALTER TABLE uploads ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ")
        )
        connection.execute(
            text(
                "ALTER TABLE uploads ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE uploads ADD COLUMN IF NOT EXISTS resumable_session_uri TEXT"
            )
        )
        connection.execute(
            text("UPDATE uploads SET retry_count = 0 WHERE retry_count IS NULL")
        )
        connection.execute(
            text("UPDATE uploads SET max_retries = 3 WHERE max_retries IS NULL")
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_youtube_accounts_user_channel ON youtube_accounts (user_id, channel_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_uploads_status_retry ON uploads (status, next_retry_at)"
            )
        )


def get_db():
    require_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
