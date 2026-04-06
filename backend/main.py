from datetime import datetime, timedelta, timezone
import asyncio
import html
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import List

from auth import get_current_user
from config import settings
from database import SessionLocal, engine, get_db, init_db
from metadata_gen import generate_upload_metadata
from models import OAuthState, Upload, User, Video, YouTubeAccount
from script_gen import generate_script
from image_gen import create_black_placeholder_image, generate_image
from audio_gen import generate_audio
from storage import get_backend_for_provider, storage_backend
from video_gen import (
    THUMBNAIL_VARIANTS,
    assemble_video,
    create_thumbnail_variants,
    create_thumbnail_variants_from_video,
)
from youtube_oauth import (
    exchange_code_for_account,
    build_google_auth_url,
    generate_code_verifier,
)
from youtube_upload import (
    PermanentUploadError,
    RetryableUploadError,
    upload_video_to_youtube,
)

active_upload_jobs: set[str] = set()


class ScriptRequest(BaseModel):
    topic: str
    style: str
    duration: str


class SceneData(BaseModel):
    scene_number: int
    narration: str
    image_prompt: str


class ScriptPayload(BaseModel):
    title: str
    scenes: List[SceneData]


class RenderRequest(BaseModel):
    script: ScriptPayload
    voice: str


class UploadRequest(BaseModel):
    youtube_account_ids: List[str] = Field(min_length=1)
    privacy_status: str = "private"
    publish_at: datetime | None = None


class MetadataSelectionRequest(BaseModel):
    selected_title: str | None = None
    selected_thumbnail_variant: str | None = None


class ChannelPresetRequest(BaseModel):
    niche: str | None = None
    content_goal: str | None = None
    tone: str | None = None
    default_privacy: str | None = None
    default_category_id: str | None = None
    timezone: str | None = None
    preferred_hour: int | None = None
    preferred_days: List[int] | None = None
    hashtag_mode: str | None = None
    cta_style: str | None = None


class UploadSceneData(BaseModel):
    image_path: str
    audio_path: str
    duration: float
    narration: str


def ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_selected_title(metadata: dict | None) -> str | None:
    if not metadata:
        return None
    return metadata.get("selected_title") or metadata.get("title")


def get_selected_thumbnail_variant(metadata: dict | None) -> str:
    if not metadata:
        return "headline"
    return metadata.get("selected_thumbnail_variant") or "headline"


def merge_upload_metadata(
    previous_metadata: dict | None, next_metadata: dict | None
) -> dict | None:
    if next_metadata is None:
        return previous_metadata
    if previous_metadata is None:
        next_metadata["selected_title"] = next_metadata.get("title")
        next_metadata["selected_thumbnail_variant"] = "headline"
        return next_metadata

    next_metadata["selected_title"] = (
        previous_metadata.get("selected_title")
        or previous_metadata.get("title")
        or next_metadata.get("title")
    )
    next_metadata["selected_thumbnail_variant"] = (
        previous_metadata.get("selected_thumbnail_variant") or "headline"
    )
    return next_metadata


def default_channel_preset(account: YouTubeAccount) -> dict:
    title = (account.channel_title or "").lower()
    niche = "general"
    tone = "clear"
    default_category_id = "22"
    content_goal = "subscriber_growth"

    if any(token in title for token in ["python", "ai", "tech", "code"]):
        niche = "technology"
        tone = "practical"
        default_category_id = "28"
        content_goal = "authority"
    elif any(token in title for token in ["history", "facts", "learn", "education"]):
        niche = "education"
        tone = "credible"
        default_category_id = "27"
        content_goal = "authority"
    elif any(token in title for token in ["story", "motivation", "mindset"]):
        niche = "motivation"
        tone = "uplifting"
        default_category_id = "22"
        content_goal = "subscriber_growth"
    elif any(token in title for token in ["game", "gaming", "funny", "memes"]):
        niche = "entertainment"
        tone = "high-energy"
        default_category_id = "24"
        content_goal = "reach"

    return {
        "niche": niche,
        "content_goal": content_goal,
        "tone": tone,
        "default_privacy": "private",
        "default_category_id": default_category_id,
        "timezone": "UTC",
        "preferred_hour": 19,
        "preferred_days": [4, 5, 6],
        "hashtag_mode": "light",
        "cta_style": "curiosity",
    }


def get_channel_preset(account: YouTubeAccount) -> dict:
    preset = default_channel_preset(account)
    if account.channel_preset_json:
        preset.update(account.channel_preset_json)
    return preset


def next_suggested_publish_time(preset: dict) -> datetime:
    timezone_name = preset.get("timezone") or "UTC"
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc

    preferred_days = preset.get("preferred_days") or [4, 5, 6]
    preferred_hour = int(preset.get("preferred_hour") or 19)
    now = datetime.now(zone)

    for day_offset in range(0, 8):
        candidate = now + timedelta(days=day_offset)
        if candidate.weekday() not in preferred_days:
            continue
        candidate = candidate.replace(
            hour=preferred_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        if candidate > now + timedelta(minutes=15):
            return candidate.astimezone(timezone.utc)

    fallback = now + timedelta(days=1)
    fallback = fallback.replace(hour=preferred_hour, minute=0, second=0, microsecond=0)
    return fallback.astimezone(timezone.utc)


def serialize_channel_schedule(preset: dict) -> dict:
    scheduled_for = next_suggested_publish_time(preset)
    return {
        "suggested_publish_at": scheduled_for.isoformat(),
        "reason": f"{preset.get('niche', 'general').title()} channel bias around {int(preset.get('preferred_hour') or 19):02d}:00 in {preset.get('timezone') or 'UTC'}",
    }


def adapt_metadata_for_channel(metadata: dict, account: YouTubeAccount) -> dict:
    preset = get_channel_preset(account)
    adapted = dict(metadata)
    selected_title = get_selected_title(metadata) or metadata.get("title") or ""
    title = selected_title

    niche = preset.get("niche") or "general"
    lowered_title = title.lower()
    if niche == "technology" and not any(
        lowered_title.startswith(prefix) for prefix in ["how", "save", "build", "use"]
    ):
        title = f"How {title}" if len(title) < 60 else title
    elif niche == "education" and "why" not in title.lower() and len(title) < 55:
        title = f"Why {title}" if not title.endswith("?") else title
    elif niche == "motivation" and len(title) < 55:
        title = f"{title} for better results"
    elif niche == "entertainment" and len(title) < 55:
        title = f"{title} in 30 seconds"

    adapted["selected_title"] = title[:100]
    adapted["category_id"] = preset.get("default_category_id") or adapted.get(
        "category_id"
    )

    hashtags = adapted.get("hashtags") or []
    if preset.get("hashtag_mode") == "none":
        hashtags = []
    elif niche == "technology":
        hashtags = hashtags[:2] + ["#TechTips"]
    elif niche == "education":
        hashtags = hashtags[:2] + ["#LearnOnShorts"]
    adapted["hashtags"] = list(dict.fromkeys(hashtags))[:3]

    description = adapted.get("description") or ""
    tone = preset.get("tone") or "clear"
    if tone == "credible":
        description = f"Clear explanation for curious viewers.\n\n{description}"
    elif tone == "high-energy":
        description = f"Fast-paced short for quick entertainment.\n\n{description}"
    elif tone == "practical":
        description = f"Use this workflow to save time.\n\n{description}"
    adapted["description"] = description[:5000]

    adapted["channel_schedule"] = serialize_channel_schedule(preset)
    adapted["channel_preset"] = preset
    return adapted


def build_visual_direction(topic: str, style: str, title: str) -> str:
    style_lens = {
        "cinematic facts": "premium cinematic editorial photography, dramatic subject lighting, rich contrast",
        "educational": "clean documentary realism, crisp lighting, grounded detail",
        "myth-busting": "bold contrast, high-energy realism, dramatic reveal framing",
        "story": "emotional cinematic storytelling, layered depth, atmospheric lighting",
        "fast-paced listicle": "high-energy visual storytelling, punchy composition, vivid color separation",
        "motivational": "uplifting cinematic realism, warm highlights, aspirational framing",
    }
    base_style = style_lens.get(
        style.lower(), "cinematic short-form realism, premium lighting"
    )
    return (
        f"Unified visual direction for '{title}' about {topic}: {base_style}, cohesive color palette across all scenes, "
        "consistent lens language, strong subject separation, premium realistic detail, vertical composition, centered focal subject, room for captions"
    )


def serialize_account(account: YouTubeAccount) -> dict:
    preset = get_channel_preset(account)
    return {
        "id": account.id,
        "channel_id": account.channel_id,
        "channel_title": account.channel_title,
        "thumbnail_url": account.thumbnail_url,
        "status": account.status,
        "preset": preset,
        "schedule_recommendation": serialize_channel_schedule(preset),
    }


def serialize_upload(upload: Upload, account: YouTubeAccount | None = None) -> dict:
    youtube_account = account or upload.youtube_account
    return {
        "id": upload.id,
        "status": upload.status,
        "title": upload.title,
        "description": upload.description,
        "tags": upload.tags_json or [],
        "privacy_status": upload.privacy_status,
        "publish_at": upload.publish_at.isoformat() if upload.publish_at else None,
        "youtube_video_id": upload.youtube_video_id,
        "youtube_url": upload.youtube_url,
        "retry_count": upload.retry_count,
        "max_retries": upload.max_retries,
        "next_retry_at": (
            upload.next_retry_at.isoformat() if upload.next_retry_at else None
        ),
        "last_attempted_at": (
            upload.last_attempted_at.isoformat() if upload.last_attempted_at else None
        ),
        "started_at": upload.started_at.isoformat() if upload.started_at else None,
        "completed_at": upload.completed_at.isoformat()
        if upload.completed_at
        else None,
        "error_message": upload.error_message,
        "youtube_account": (
            serialize_account(youtube_account) if youtube_account is not None else None
        ),
    }


def get_video_thumbnail_path(video: Video) -> str | None:
    if not video.output_path:
        return None
    selected_variant = get_selected_thumbnail_variant(video.upload_metadata_json)
    thumbnail_path = (
        f"{os.path.splitext(video.output_path)[0]}_thumbnail_{selected_variant}.jpg"
    )
    if os.path.exists(thumbnail_path):
        return thumbnail_path
    thumbnail_path = f"{os.path.splitext(video.output_path)[0]}_thumbnail_headline.jpg"
    if os.path.exists(thumbnail_path):
        return thumbnail_path
    return None


def get_video_thumbnail_variants(video: Video) -> list[dict[str, str]]:
    if not video.output_path:
        return []

    base = os.path.splitext(video.output_path)[0]
    variants: list[dict[str, str]] = []
    for variant_name, variant_label in THUMBNAIL_VARIANTS:
        candidate = f"{base}_thumbnail_{variant_name}.jpg"
        if os.path.exists(candidate):
            variants.append({"name": variant_name, "label": variant_label})
    return variants


def serialize_video(video: Video, uploads: list[Upload] | None = None) -> dict:
    upload_rows = uploads if uploads is not None else list(video.uploads)
    return {
        "id": video.id,
        "title": video.title,
        "selected_title": get_selected_title(video.upload_metadata_json),
        "topic": video.topic,
        "style": video.style,
        "duration": video.duration_label,
        "voice": video.voice,
        "script": video.script_json,
        "render_status": video.render_status,
        "render_step": video.render_step,
        "progress": {
            "completed": video.progress_completed,
            "total": video.progress_total,
        },
        "metadata": (
            {
                "duration_sec": video.duration_sec,
                "resolution": "1080x1920",
                "file_size_mb": video.file_size_mb,
                "score": (
                    (video.upload_metadata_json or {})
                    .get("retention_report", {})
                    .get("overall_score", 95)
                ),
                "retention_report": (video.upload_metadata_json or {}).get(
                    "retention_report"
                ),
                "thumbnail_available": get_video_thumbnail_path(video) is not None,
                "thumbnail_variants": get_video_thumbnail_variants(video),
                "selected_thumbnail_variant": get_selected_thumbnail_variant(
                    video.upload_metadata_json
                ),
            }
            if video.render_status == "completed"
            else None
        ),
        "upload_metadata": video.upload_metadata_json,
        "storage_provider": video.storage_provider,
        "error_message": video.error_message,
        "uploads": [serialize_upload(upload) for upload in upload_rows],
    }


def get_owned_video(db: Session, user: User, video_id: str) -> Video:
    video = db.scalar(
        select(Video).where(Video.id == video_id, Video.user_id == user.id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def update_video(video_id: str, **values) -> None:
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            return
        for key, value in values.items():
            setattr(video, key, value)
        db.commit()


def update_upload(upload_id: str, **values) -> None:
    with SessionLocal() as db:
        upload = db.get(Upload, upload_id)
        if upload is None:
            return
        for key, value in values.items():
            setattr(upload, key, value)
        db.commit()


def calculate_retry_time(retry_count: int) -> datetime:
    seconds = min(
        settings.upload_retry_max_seconds,
        settings.upload_retry_base_seconds * max(1, 2 ** max(retry_count - 1, 0)),
    )
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


def dispatch_upload_job(upload_id: str) -> bool:
    if upload_id in active_upload_jobs:
        return False

    active_upload_jobs.add(upload_id)
    task = asyncio.create_task(process_upload_job(upload_id))

    def _cleanup(_: asyncio.Task) -> None:
        active_upload_jobs.discard(upload_id)

    task.add_done_callback(_cleanup)
    return True


async def retry_dispatch_loop() -> None:
    while True:
        due_upload_ids = []
        db = None
        try:
            now = datetime.now(timezone.utc)
            db = SessionLocal()
            due_upload_ids = db.scalars(
                select(Upload.id)
                .join(Video, Upload.video_id == Video.id)
                .join(
                    YouTubeAccount,
                    Upload.youtube_account_id == YouTubeAccount.id,
                )
                .where(
                    Upload.status.in_(["queued", "retry_scheduled"]),
                    or_(Upload.next_retry_at.is_(None), Upload.next_retry_at <= now),
                    Video.render_status == "completed",
                    YouTubeAccount.status == "connected",
                )
                .order_by(Upload.created_at.asc())
                .limit(10)
            ).all()

            for upload_id in due_upload_ids:
                dispatch_upload_job(upload_id)
        except asyncio.CancelledError:
            raise
        except SQLAlchemyError as exc:
            if engine is not None:
                engine.dispose()
            print(f"Upload retry loop database issue: {exc}")
        except Exception:
            traceback.print_exc()
        finally:
            if db is not None:
                try:
                    db.close()
                except SQLAlchemyError:
                    if engine is not None:
                        engine.dispose()

        await asyncio.sleep(5)


def build_popup_response(success: bool, message: str) -> HTMLResponse:
    escaped_message = html.escape(message)
    escaped_frontend_origin = html.escape(settings.frontend_url, quote=True)
    escaped_message_attr = html.escape(message, quote=True)
    body = f"""
    <!doctype html>
    <html>
      <body style=\"font-family:Arial,sans-serif;background:#0f172a;color:#f8fafc;padding:24px;\">
        <h2>{"YouTube account connected" if success else "Connection failed"}</h2>
        <p>{escaped_message}</p>
        <div
          id="oauth-result"
          data-success="{str(success).lower()}"
          data-message="{escaped_message_attr}"
          data-origin="{escaped_frontend_origin}"
        ></div>
        <script>
          const resultNode = document.getElementById('oauth-result');
          const targetOrigin = resultNode?.dataset.origin || '/';
          const popupMessage = resultNode?.dataset.message || '';
          const popupSuccess = resultNode?.dataset.success === 'true';
          if (window.opener) {{
            window.opener.postMessage({{
              type: 'youtube-connected',
              success: popupSuccess,
              message: popupMessage
            }}, targetOrigin);
          }}
          window.close();
        </script>
      </body>
    </html>
    """
    return HTMLResponse(body)


async def process_video_job(video_id: str):
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            return
        script = video.script_json
        voice = video.voice or "Sarah"
        title = video.title
        topic = video.topic
        style = video.style

    scenes = script.get("scenes") or []
    total_assets = len(scenes) * 2
    session_id = uuid.uuid4().hex[:8]
    visual_direction = build_visual_direction(topic, style, title)
    update_video(
        video_id,
        render_status="rendering",
        render_step="assets",
        progress_completed=0,
        progress_total=total_assets,
        error_message=None,
        output_path=None,
        upload_metadata_json=None,
    )

    try:
        scenes_data = [None] * len(scenes)
        completed = 0
        progress_lock = asyncio.Lock()
        scene_semaphore = asyncio.Semaphore(settings.scene_concurrency)

        async def render_scene(index: int, scene: dict):
            nonlocal completed

            async with scene_semaphore:
                image_result, audio_result = await asyncio.gather(
                    generate_image(
                        scene["image_prompt"],
                        index,
                        session_id,
                        visual_direction=visual_direction,
                    ),
                    generate_audio(scene["narration"], index, session_id, voice),
                    return_exceptions=True,
                )

            if isinstance(audio_result, Exception):
                raise audio_result

            if isinstance(image_result, Exception):
                print(
                    f"Scene {index} image generation failed: {type(image_result).__name__}: {image_result}"
                )
                image_path = await create_black_placeholder_image(
                    index,
                    session_id,
                    scene.get("image_prompt") or scene.get("narration"),
                )
            else:
                image_path = image_result

            scenes_data[index] = {
                "image_path": image_path,
                "audio_path": audio_result["path"],
                "duration": audio_result["duration"],
                "narration": scene["narration"],
            }

            async with progress_lock:
                completed += 2
                update_video(
                    video_id,
                    render_status="rendering",
                    render_step="assets",
                    progress_completed=completed,
                    progress_total=total_assets,
                )

        results = await asyncio.gather(
            *(render_scene(index, scene) for index, scene in enumerate(scenes)),
            return_exceptions=True,
        )

        for index, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Scene {index} failed: {type(result).__name__}: {result}")

        scenes_data = [scene for scene in scenes_data if scene is not None]

        update_video(video_id, render_step="video")
        output_path = await assemble_video(scenes_data, title, session_id)
        thumbnail_variants = await create_thumbnail_variants(
            scenes_data[0]["image_path"], title, session_id
        )
        file_size = round(os.path.getsize(output_path) / (1024 * 1024), 2)
        filename = os.path.basename(output_path)
        stored_file = await asyncio.to_thread(
            storage_backend.persist_video,
            output_path,
            video_id,
            filename,
        )
        duration_sec = round(sum(scene["duration"] for scene in scenes_data), 1)
        local_output_path = storage_backend.resolve_local_path(stored_file.key)
        if local_output_path:
            for variant in thumbnail_variants:
                variant_path = variant["path"]
                if os.path.exists(variant_path):
                    thumbnail_output_path = f"{os.path.splitext(local_output_path)[0]}_thumbnail_{variant['name']}.jpg"
                    os.replace(variant_path, thumbnail_output_path)
        try:
            generated_metadata = await generate_upload_metadata(
                topic=topic,
                style=style,
                duration=video.duration_label,
                script=script,
            )
            upload_metadata = merge_upload_metadata(None, generated_metadata)
        except Exception as metadata_error:
            print(f"Upload metadata generation failed: {metadata_error}")
            upload_metadata = None

        update_video(
            video_id,
            render_status="completed",
            render_step="done",
            progress_completed=total_assets,
            progress_total=total_assets,
            output_path=local_output_path,
            storage_provider=stored_file.provider,
            storage_key=stored_file.key,
            output_filename=stored_file.filename,
            output_mime_type=stored_file.mime_type,
            file_size_mb=file_size,
            duration_sec=duration_sec,
            upload_metadata_json=upload_metadata,
        )
    except Exception as exc:
        traceback.print_exc()
        update_video(
            video_id,
            render_status="failed",
            render_step="script",
            error_message=f"{type(exc).__name__}: {exc}",
        )


async def process_upload_job(upload_id: str):
    with SessionLocal() as db:
        upload = db.get(Upload, upload_id)
        if upload is None:
            return
        video = db.get(Video, upload.video_id)
        account = db.get(YouTubeAccount, upload.youtube_account_id)

    if video is None or account is None:
        update_upload(
            upload_id, status="failed", error_message="Upload prerequisites missing."
        )
        return

    if account.status != "connected":
        update_upload(
            upload_id,
            status="failed",
            error_message="Reconnect the YouTube account before uploading.",
        )
        return

    if not video.storage_key and (
        not video.output_path or not os.path.exists(video.output_path)
    ):
        update_upload(
            upload_id,
            status="failed",
            error_message="Rendered video file was not found.",
        )
        return

    upload.publish_at = ensure_utc_datetime(upload.publish_at)
    if upload.publish_at and upload.publish_at <= datetime.now(timezone.utc):
        upload.publish_at = None

    materialized_path = None
    file_backend = None
    try:
        if video.storage_key:
            file_backend = get_backend_for_provider(video.storage_provider)
            materialized_path = await asyncio.to_thread(
                file_backend.materialize, video.storage_key
            )
        else:
            materialized_path = video.output_path

        update_upload(
            upload_id,
            status="uploading",
            error_message=None,
            last_attempted_at=datetime.now(timezone.utc),
            started_at=upload.started_at or datetime.now(timezone.utc),
            next_retry_at=None,
        )

        result = await asyncio.to_thread(
            upload_video_to_youtube,
            materialized_path,
            account,
            {
                "title": upload.title,
                "description": upload.description,
                "tags": upload.tags_json or [],
                "category_id": upload.category_id,
                "privacy_status": upload.privacy_status,
                "publish_at": upload.publish_at,
            },
            upload.resumable_session_uri,
        )

        with SessionLocal() as db:
            db_account = db.get(YouTubeAccount, account.id)
            db_upload = db.get(Upload, upload_id)
            if db_account is None or db_upload is None:
                return

            for key, value in result["credentials"].items():
                setattr(db_account, key, value)

            db_upload.status = "completed"
            db_upload.youtube_video_id = result["youtube_video_id"]
            db_upload.youtube_url = result["youtube_url"]
            db_upload.completed_at = datetime.now(timezone.utc)
            db_upload.resumable_session_uri = None
            db_upload.error_message = None
            db.commit()
    except RetryableUploadError as exc:
        traceback.print_exc()
        next_retry_count = upload.retry_count + 1
        if next_retry_count <= upload.max_retries:
            update_upload(
                upload_id,
                status="retry_scheduled",
                retry_count=next_retry_count,
                next_retry_at=calculate_retry_time(next_retry_count),
                resumable_session_uri=exc.session_uri or upload.resumable_session_uri,
                error_message=str(exc),
            )
        else:
            update_upload(
                upload_id,
                status="failed",
                retry_count=next_retry_count,
                resumable_session_uri=exc.session_uri or upload.resumable_session_uri,
                error_message=str(exc),
            )
    except PermanentUploadError as exc:
        traceback.print_exc()
        update_upload(
            upload_id,
            status="failed",
            resumable_session_uri=exc.session_uri,
            error_message=str(exc),
        )
    except Exception as exc:
        traceback.print_exc()
        next_retry_count = upload.retry_count + 1
        if next_retry_count <= upload.max_retries:
            update_upload(
                upload_id,
                status="retry_scheduled",
                retry_count=next_retry_count,
                next_retry_at=calculate_retry_time(next_retry_count),
                resumable_session_uri=upload.resumable_session_uri,
                error_message=str(exc),
            )
        else:
            update_upload(upload_id, status="failed", error_message=str(exc))
    finally:
        if materialized_path and file_backend and video.storage_key:
            await asyncio.to_thread(
                file_backend.cleanup_materialized, materialized_path, video.storage_key
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    app.state.upload_retry_task = asyncio.create_task(retry_dispatch_loop())
    try:
        yield
    finally:
        retry_task = getattr(app.state, "upload_retry_task", None)
        if retry_task is not None:
            retry_task.cancel()
            try:
                await retry_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="AI Shorts Generator API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/generate-script")
async def api_generate_script(
    req: ScriptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        script = await generate_script(req.topic, req.style, req.duration)
        video = Video(
            user_id=current_user.id,
            title=script["title"],
            topic=req.topic,
            style=req.style,
            duration_label=req.duration,
            script_json=script,
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        return {"video_id": video.id, **script}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to generate script.")


@app.post("/videos/{video_id}/render")
async def api_render_video(
    video_id: str,
    req: RenderRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    if video.render_status == "rendering":
        raise HTTPException(status_code=409, detail="Video is already rendering.")

    video.title = req.script.title
    video.voice = req.voice
    video.script_json = req.script.model_dump()
    video.render_status = "queued"
    video.render_step = "assets"
    video.progress_completed = 0
    video.progress_total = len(req.script.scenes) * 2
    video.error_message = None
    video.output_path = None
    video.storage_provider = None
    video.storage_key = None
    video.output_filename = None
    video.output_mime_type = None
    db.commit()

    background_tasks.add_task(process_video_job, video.id)
    return serialize_video(video, [])


@app.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "clerk_user_id": current_user.clerk_user_id}


@app.get("/videos/{video_id}")
async def get_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    uploads = db.scalars(
        select(Upload)
        .where(Upload.video_id == video.id)
        .order_by(Upload.created_at.desc())
    ).all()
    for upload in uploads:
        upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
    return serialize_video(video, uploads)


@app.get("/videos/{video_id}/download")
async def download_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    if video.render_status != "completed":
        raise HTTPException(status_code=404, detail="Video is not ready yet.")

    if video.storage_key:
        video_storage = get_backend_for_provider(video.storage_provider)
        local_path = video_storage.resolve_local_path(video.storage_key)
        filename = video.output_filename or os.path.basename(video.storage_key)
        media_type = video.output_mime_type or "video/mp4"

        if local_path:
            if not os.path.exists(local_path):
                raise HTTPException(
                    status_code=404, detail="Rendered file was not found."
                )
            return FileResponse(local_path, media_type=media_type, filename=filename)

        return StreamingResponse(
            video_storage.open_stream(video.storage_key),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    if not video.output_path or not os.path.exists(video.output_path):
        raise HTTPException(status_code=404, detail="Rendered file was not found.")

    filename = os.path.basename(video.output_path)
    return FileResponse(video.output_path, media_type="video/mp4", filename=filename)


@app.get("/videos/{video_id}/thumbnail")
async def download_video_thumbnail(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    if video.render_status != "completed":
        raise HTTPException(status_code=404, detail="Thumbnail is not ready yet.")

    thumbnail_path = get_video_thumbnail_path(video)
    if not thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail was not found.")

    filename = os.path.basename(thumbnail_path)
    return FileResponse(thumbnail_path, media_type="image/jpeg", filename=filename)


@app.get("/videos/{video_id}/thumbnail/{variant_name}")
async def download_video_thumbnail_variant(
    video_id: str,
    variant_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    if video.render_status != "completed":
        raise HTTPException(status_code=404, detail="Thumbnail is not ready yet.")

    variants = {item["name"] for item in get_video_thumbnail_variants(video)}
    if variant_name not in variants:
        raise HTTPException(status_code=404, detail="Thumbnail variant was not found.")

    variant_path = (
        f"{os.path.splitext(video.output_path)[0]}_thumbnail_{variant_name}.jpg"
    )
    filename = os.path.basename(variant_path)
    return FileResponse(variant_path, media_type="image/jpeg", filename=filename)


@app.patch("/videos/{video_id}/publish-selection")
async def update_publish_selection(
    video_id: str,
    req: MetadataSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    metadata = video.upload_metadata_json or {}
    if not metadata:
        raise HTTPException(status_code=409, detail="Upload metadata is not ready yet.")

    if req.selected_title:
        metadata["selected_title"] = req.selected_title.strip()

    if req.selected_thumbnail_variant:
        available_variants = {
            item["name"] for item in get_video_thumbnail_variants(video)
        }
        if req.selected_thumbnail_variant not in available_variants:
            raise HTTPException(status_code=404, detail="Thumbnail variant not found.")
        metadata["selected_thumbnail_variant"] = req.selected_thumbnail_variant

    video.upload_metadata_json = metadata
    db.commit()
    db.refresh(video)
    uploads = db.scalars(
        select(Upload)
        .where(Upload.video_id == video.id)
        .order_by(Upload.created_at.desc())
    ).all()
    for upload in uploads:
        upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
    return serialize_video(video, uploads)


@app.post("/videos/{video_id}/metadata/regenerate")
async def regenerate_video_metadata(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    generated_metadata = await generate_upload_metadata(
        topic=video.topic,
        style=video.style,
        duration=video.duration_label,
        script=video.script_json,
    )
    video.upload_metadata_json = merge_upload_metadata(
        video.upload_metadata_json, generated_metadata
    )
    db.commit()
    db.refresh(video)
    uploads = db.scalars(
        select(Upload)
        .where(Upload.video_id == video.id)
        .order_by(Upload.created_at.desc())
    ).all()
    for upload in uploads:
        upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
    return serialize_video(video, uploads)


@app.post("/videos/{video_id}/thumbnails/regenerate")
async def regenerate_video_thumbnails(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    if video.render_status != "completed":
        raise HTTPException(
            status_code=409, detail="Render the video before regenerating thumbnails."
        )

    if not video.output_path or not os.path.exists(video.output_path):
        raise HTTPException(
            status_code=404, detail="Rendered video file was not found."
        )

    session_id = uuid.uuid4().hex[:8]
    variants = await create_thumbnail_variants_from_video(
        video.output_path, video.title, session_id
    )
    for variant in variants:
        variant_path = variant["path"]
        if os.path.exists(variant_path):
            destination = f"{os.path.splitext(video.output_path)[0]}_thumbnail_{variant['name']}.jpg"
            os.replace(variant_path, destination)

    metadata = video.upload_metadata_json or {}
    metadata["selected_thumbnail_variant"] = (
        metadata.get("selected_thumbnail_variant") or "headline"
    )
    video.upload_metadata_json = metadata
    db.commit()
    db.refresh(video)
    uploads = db.scalars(
        select(Upload)
        .where(Upload.video_id == video.id)
        .order_by(Upload.created_at.desc())
    ).all()
    for upload in uploads:
        upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
    return serialize_video(video, uploads)


@app.get("/youtube/accounts")
async def list_youtube_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = db.scalars(
        select(YouTubeAccount).where(
            YouTubeAccount.user_id == current_user.id,
            YouTubeAccount.status == "connected",
        )
    ).all()
    return {"accounts": [serialize_account(account) for account in accounts]}


@app.post("/youtube/connect/start")
async def start_youtube_connect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        state = uuid.uuid4().hex
        code_verifier = generate_code_verifier()
        db.execute(delete(OAuthState).where(OAuthState.user_id == current_user.id))
        db.add(
            OAuthState(
                state=state,
                user_id=current_user.id,
                code_verifier=code_verifier,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )
        db.commit()
        return {"auth_url": build_google_auth_url(state, code_verifier)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/youtube/connect/callback")
async def youtube_connect_callback(
    state: str,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        return build_popup_response(False, f"Google returned an error: {error}")

    oauth_state = db.get(OAuthState, state)
    oauth_expires_at = (
        ensure_utc_datetime(oauth_state.expires_at) if oauth_state else None
    )
    if (
        oauth_state is None
        or oauth_expires_at is None
        or oauth_expires_at < datetime.now(timezone.utc)
    ):
        if oauth_state is not None:
            db.delete(oauth_state)
            db.commit()
        return build_popup_response(
            False, "This Google connection link expired. Start the connection again."
        )

    if not code:
        return build_popup_response(False, "Missing Google authorization code.")

    if not oauth_state.code_verifier:
        db.delete(oauth_state)
        db.commit()
        return build_popup_response(
            False,
            "This Google connection session is invalid. Start the connection again.",
        )

    try:
        account_data = exchange_code_for_account(code, state, oauth_state.code_verifier)
        existing_account = db.scalar(
            select(YouTubeAccount).where(
                YouTubeAccount.user_id == oauth_state.user_id,
                YouTubeAccount.channel_id == account_data["channel_id"],
            )
        )

        if existing_account is None:
            existing_account = YouTubeAccount(
                user_id=oauth_state.user_id, **account_data
            )
            db.add(existing_account)
        else:
            for key, value in account_data.items():
                setattr(existing_account, key, value)
            existing_account.status = "connected"

        db.delete(oauth_state)
        db.commit()
        return build_popup_response(
            True, f"Connected {existing_account.channel_title} successfully."
        )
    except Exception as exc:
        traceback.print_exc()
        db.delete(oauth_state)
        db.commit()
        return build_popup_response(False, str(exc))


@app.delete("/youtube/accounts/{account_id}")
async def disconnect_youtube_account(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = db.scalar(
        select(YouTubeAccount).where(
            YouTubeAccount.id == account_id,
            YouTubeAccount.user_id == current_user.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="YouTube account not found")

    account.status = "disconnected"
    account.access_token_encrypted = None
    account.refresh_token_encrypted = None
    account.token_expires_at = None
    db.commit()
    return {"success": True}


@app.patch("/youtube/accounts/{account_id}/preset")
async def update_youtube_account_preset(
    account_id: str,
    req: ChannelPresetRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = db.scalar(
        select(YouTubeAccount).where(
            YouTubeAccount.id == account_id,
            YouTubeAccount.user_id == current_user.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="YouTube account not found")

    preset = get_channel_preset(account)
    for field in [
        "niche",
        "content_goal",
        "tone",
        "default_privacy",
        "default_category_id",
        "timezone",
        "preferred_hour",
        "preferred_days",
        "hashtag_mode",
        "cta_style",
    ]:
        value = getattr(req, field)
        if value is not None:
            preset[field] = value

    account.channel_preset_json = preset
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@app.get("/videos/{video_id}/channel-preview/{account_id}")
async def get_channel_preview(
    video_id: str,
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    account = db.scalar(
        select(YouTubeAccount).where(
            YouTubeAccount.id == account_id,
            YouTubeAccount.user_id == current_user.id,
            YouTubeAccount.status == "connected",
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="YouTube account not found")

    metadata = video.upload_metadata_json
    if metadata is None:
        metadata = await generate_upload_metadata(
            topic=video.topic,
            style=video.style,
            duration=video.duration_label,
            script=video.script_json,
        )
        video.upload_metadata_json = merge_upload_metadata(
            video.upload_metadata_json, metadata
        )
        db.commit()
        db.refresh(video)
        metadata = video.upload_metadata_json

    return adapt_metadata_for_channel(metadata, account)


@app.post("/videos/{video_id}/upload")
async def upload_video(
    video_id: str,
    req: UploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    video = get_owned_video(db, current_user, video_id)
    if video.render_status != "completed":
        raise HTTPException(
            status_code=409, detail="Render the video before uploading it."
        )

    accounts = db.scalars(
        select(YouTubeAccount).where(
            YouTubeAccount.user_id == current_user.id,
            YouTubeAccount.id.in_(req.youtube_account_ids),
            YouTubeAccount.status == "connected",
        )
    ).all()

    if len(accounts) != len(set(req.youtube_account_ids)):
        raise HTTPException(
            status_code=404, detail="One or more YouTube accounts were not found."
        )

    publish_at = ensure_utc_datetime(req.publish_at)
    if publish_at and publish_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=422,
            detail="publish_at must be a future timestamp.",
        )

    metadata = video.upload_metadata_json
    if metadata is None:
        metadata = await generate_upload_metadata(
            topic=video.topic,
            style=video.style,
            duration=video.duration_label,
            script=video.script_json,
        )
        video.upload_metadata_json = metadata
        db.commit()

    created_uploads = []
    for account in accounts:
        adapted_metadata = adapt_metadata_for_channel(metadata, account)
        account_preset = get_channel_preset(account)
        effective_privacy = (
            account_preset.get("default_privacy") or "private"
            if req.privacy_status == "channel_default"
            else req.privacy_status
            or account_preset.get("default_privacy")
            or "private"
        )
        effective_publish_at = publish_at
        if (
            effective_publish_at is None
            and adapted_metadata.get("suggested_publish_mode") == "scheduled"
        ):
            effective_publish_at = ensure_utc_datetime(
                datetime.fromisoformat(
                    adapted_metadata.get("channel_schedule", {}).get(
                        "suggested_publish_at"
                    )
                )
                if adapted_metadata.get("channel_schedule", {}).get(
                    "suggested_publish_at"
                )
                else None
            )

        upload = Upload(
            video_id=video.id,
            youtube_account_id=account.id,
            status="queued",
            title=get_selected_title(adapted_metadata) or adapted_metadata["title"],
            description=adapted_metadata["description"],
            tags_json=adapted_metadata.get("tags") or [],
            category_id=adapted_metadata.get("category_id") or "22",
            privacy_status=effective_privacy,
            publish_at=effective_publish_at,
            max_retries=settings.upload_retry_default_attempts,
        )
        db.add(upload)
        db.flush()
        created_uploads.append(upload)

    db.commit()
    for upload in created_uploads:
        db.refresh(upload)
        upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
        dispatch_upload_job(upload.id)

    return {"uploads": [serialize_upload(upload) for upload in created_uploads]}


@app.post("/uploads/{upload_id}/retry")
async def retry_upload(
    upload_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    upload = db.scalar(
        select(Upload)
        .join(Video, Upload.video_id == Video.id)
        .join(YouTubeAccount, Upload.youtube_account_id == YouTubeAccount.id)
        .where(
            Upload.id == upload_id,
            Video.user_id == current_user.id,
        )
    )
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")

    upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
    if upload.youtube_account is None or upload.youtube_account.status != "connected":
        raise HTTPException(
            status_code=409,
            detail="Reconnect the YouTube account before retrying this upload.",
        )

    if upload.status == "completed":
        raise HTTPException(status_code=409, detail="This upload is already completed.")

    upload.status = "queued"
    upload.error_message = None
    upload.next_retry_at = datetime.now(timezone.utc)
    upload.retry_count = 0
    upload.completed_at = None
    db.commit()
    db.refresh(upload)
    upload.youtube_account = db.get(YouTubeAccount, upload.youtube_account_id)
    dispatch_upload_job(upload.id)
    return serialize_upload(upload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
