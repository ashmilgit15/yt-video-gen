from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    videos: Mapped[list["Video"]] = relationship(back_populates="user")
    youtube_accounts: Mapped[list["YouTubeAccount"]] = relationship(
        back_populates="user"
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str] = mapped_column(String(500))
    style: Mapped[str] = mapped_column(String(100))
    duration_label: Mapped[str] = mapped_column(String(32))
    voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    script_json: Mapped[dict] = mapped_column(JSON)
    render_status: Mapped[str] = mapped_column(String(32), default="script_ready")
    render_step: Mapped[str] = mapped_column(String(32), default="script")
    progress_completed: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    upload_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="videos")
    uploads: Mapped[list["Upload"]] = relationship(back_populates="video")


class YouTubeAccount(Base):
    __tablename__ = "youtube_accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel_id: Mapped[str] = mapped_column(String(255), index=True)
    channel_title: Mapped[str] = mapped_column(String(255))
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    channel_preset_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="connected")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="youtube_accounts")
    uploads: Mapped[list["Upload"]] = relationship(back_populates="youtube_account")


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    youtube_account_id: Mapped[str] = mapped_column(
        ForeignKey("youtube_accounts.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    tags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    category_id: Mapped[str] = mapped_column(String(32), default="22")
    privacy_status: Mapped[str] = mapped_column(String(32), default="private")
    publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    youtube_video_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resumable_session_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    video: Mapped[Video] = relationship(back_populates="uploads")
    youtube_account: Mapped[YouTubeAccount] = relationship(back_populates="uploads")


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code_verifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
