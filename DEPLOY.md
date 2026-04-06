# Free Deploy Guide

## Recommended stack

- Frontend: Vercel Hobby
- Backend: Google Cloud Run
- Database: Neon Free
- Auth: Clerk Hobby
- Video storage: Cloudflare R2 free tier

This is the closest practical `free` setup for the current app.

## Why this stack

- Vercel Hobby is free for the Vite frontend.
- Cloud Run has a real free tier and can run the FastAPI + FFmpeg backend in a container.
- Neon Free already fits the database layer used by this app.
- Clerk Hobby is free for low usage.
- Cloudflare R2 has a free tier and works with the S3-compatible storage backend already implemented.

## Important reality check

This app does AI generation, FFmpeg video rendering, and YouTube uploads. Hosting can stay free at low usage, but these parts can still become the real limit:

- Gemini / OpenRouter / other AI API usage
- YouTube API quota for uploads
- Cloud Run compute if rendering volume grows

## 1. Deploy the frontend to Vercel

Project root for Vercel:

```text
frontend
```

Environment variables:

```env
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
VITE_API_BASE_URL=https://YOUR_BACKEND_URL
```

## 2. Deploy the backend to Cloud Run

Project root for Cloud Run:

```text
backend
```

Use the included `backend/Dockerfile`.

Suggested Cloud Run settings:

- Region: `us-central1`
- CPU: `1`
- Memory: `1Gi` or `2Gi`
- Concurrency: `1`
- Timeout: `900` seconds
- Min instances: `0`

Example deploy command:

```bash
gcloud run deploy ai-video-backend \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 2Gi \
  --concurrency 1 \
  --timeout 900
```

## 3. Set backend environment variables in Cloud Run

```env
DATABASE_URL=your_neon_connection_string
FRONTEND_URL=https://YOUR_VERCEL_URL
CLERK_SECRET_KEY=your_clerk_secret_key
CLERK_AUTHORIZED_PARTIES=https://YOUR_VERCEL_URL

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=https://YOUR_BACKEND_URL/youtube/connect/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=your_fernet_key

GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
POLLINATIONS_API_KEY=...
DEFAULT_TTS=edge

STORAGE_BACKEND=s3
STORAGE_S3_BUCKET=your_r2_bucket
STORAGE_S3_REGION=auto
STORAGE_S3_ENDPOINT_URL=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
STORAGE_S3_ACCESS_KEY_ID=your_r2_access_key
STORAGE_S3_SECRET_ACCESS_KEY=your_r2_secret_key
STORAGE_S3_PREFIX=ai-video-website

UPLOAD_RETRY_BASE_SECONDS=30
UPLOAD_RETRY_MAX_SECONDS=900
UPLOAD_RETRY_DEFAULT_ATTEMPTS=3
```

## 4. Set Google OAuth production values

In Google Cloud Console, add:

Authorized JavaScript origin:

```text
https://YOUR_VERCEL_URL
```

Authorized redirect URI:

```text
https://YOUR_BACKEND_URL/youtube/connect/callback
```

## 5. Update Clerk production settings

In Clerk:

- Add your Vercel domain as an allowed production domain.
- Use the production publishable key in Vercel.
- Use the production secret key in Cloud Run.

## 6. Use R2 instead of local storage in production

Cloud Run filesystem is ephemeral, so production should not use:

```env
STORAGE_BACKEND=local
```

Use `s3` with Cloudflare R2 instead.

## 7. Free-tier caveats

- Cloud Run free tier is usually enough for hobby use, not sustained rendering.
- Render has a free web service tier, but it is too weak for this FFmpeg-heavy backend.
- Railway is not fully free long-term.
- Koyeb is not the best free option for this app.

## Best practical answer

If you want the best shot at staying at `$0`:

1. Frontend on Vercel Hobby
2. Backend on Cloud Run free tier
3. Neon Free
4. Clerk Hobby
5. Cloudflare R2 free tier

If usage grows, the first thing that will usually stop being truly free is the backend compute or the AI APIs, not the frontend.
