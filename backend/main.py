from datetime import datetime, timedelta, timezone
import asyncio
import html
import os
import traceback
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session
from typing import List

from auth import get_current_user
from config import settings
from database import SessionLocal, get_db, init_db
from metadata_gen import generate_upload_metadata
from models import OAuthState, Upload, User, Video, YouTubeAccount
from script_gen import generate_script
from image_gen import generate_image
from audio_gen import generate_audio
from storage import get_backend_for_provider, storage_backend
from video_gen import assemble_video
from youtube_oauth import exchange_code_for_account, build_google_auth_url
from youtube_upload import (
    PermanentUploadError,
    RetryableUploadError,
    upload_video_to_youtube,
)

app = FastAPI(title="AI Shorts Generator API")
active_upload_jobs: set[str] = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class UploadSceneData(BaseModel):
    image_path: str
    audio_path: str
    duration: float
    narration: str


def serialize_account(account: YouTubeAccount) -> dict:
    return {
        "id": account.id,
        "channel_id": account.channel_id,
        "channel_title": account.channel_title,
        "thumbnail_url": account.thumbnail_url,
        "status": account.status,
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


def serialize_video(video: Video, uploads: list[Upload] | None = None) -> dict:
    upload_rows = uploads if uploads is not None else list(video.uploads)
    return {
        "id": video.id,
        "title": video.title,
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
                "score": 95,
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
        try:
            now = datetime.now(timezone.utc)
            with SessionLocal() as db:
                due_upload_ids = db.scalars(
                    select(Upload.id)
                    .join(Video, Upload.video_id == Video.id)
                    .join(
                        YouTubeAccount,
                        Upload.youtube_account_id == YouTubeAccount.id,
                    )
                    .where(
                        Upload.status.in_(["queued", "retry_scheduled"]),
                        or_(
                            Upload.next_retry_at.is_(None), Upload.next_retry_at <= now
                        ),
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
        except Exception:
            traceback.print_exc()

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

    scenes = script.get("scenes") or []
    total_assets = len(scenes) * 2
    session_id = uuid.uuid4().hex[:8]
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
        scenes_data = []
        completed = 0

        for index, scene in enumerate(scenes):
            image_path, audio_result = await asyncio.gather(
                generate_image(scene["image_prompt"], index, session_id),
                generate_audio(scene["narration"], index, session_id, voice),
            )
            completed += 2
            update_video(
                video_id,
                render_status="rendering",
                render_step="assets",
                progress_completed=completed,
                progress_total=total_assets,
            )
            scenes_data.append(
                {
                    "image_path": image_path,
                    "audio_path": audio_result["path"],
                    "duration": audio_result["duration"],
                    "narration": scene["narration"],
                }
            )

        update_video(video_id, render_step="video")
        output_path = await assemble_video(scenes_data, title, session_id)
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


@app.on_event("startup")
async def on_startup():
    init_db()
    app.state.upload_retry_task = asyncio.create_task(retry_dispatch_loop())


@app.on_event("shutdown")
async def on_shutdown():
    retry_task = getattr(app.state, "upload_retry_task", None)
    if retry_task is not None:
        retry_task.cancel()
        try:
            await retry_task
        except asyncio.CancelledError:
            pass


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
        db.execute(delete(OAuthState).where(OAuthState.user_id == current_user.id))
        db.add(
            OAuthState(
                state=state,
                user_id=current_user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            )
        )
        db.commit()
        return {"auth_url": build_google_auth_url(state)}
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
    if oauth_state is None or oauth_state.expires_at < datetime.now(timezone.utc):
        if oauth_state is not None:
            db.delete(oauth_state)
            db.commit()
        return build_popup_response(
            False, "This Google connection link expired. Start the connection again."
        )

    if not code:
        return build_popup_response(False, "Missing Google authorization code.")

    try:
        account_data = exchange_code_for_account(code, state)
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

    if req.publish_at and req.publish_at <= datetime.now(timezone.utc):
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
        upload = Upload(
            video_id=video.id,
            youtube_account_id=account.id,
            status="queued",
            title=metadata["title"],
            description=metadata["description"],
            tags_json=metadata.get("tags") or [],
            category_id=metadata.get("category_id") or "22",
            privacy_status=req.privacy_status,
            publish_at=req.publish_at,
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

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
