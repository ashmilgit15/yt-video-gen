# Development Setup

## Clerk React (Vite)

Clerk quickstart: https://clerk.com/docs/react/getting-started/quickstart

Frontend uses:

`frontend/.env.local`

```env
VITE_CLERK_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
VITE_API_BASE_URL=http://localhost:8000
```

Backend uses:

`backend/.env`

```env
CLERK_SECRET_KEY=YOUR_CLERK_SECRET_KEY
CLERK_AUTHORIZED_PARTIES=http://localhost:5173
```

## Google OAuth for YouTube

Create a Google OAuth client of type `Web application`.

Required redirect URI:

```text
http://localhost:8000/youtube/connect/callback
```

Add to `backend/.env`:

```env
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://localhost:8000/youtube/connect/callback
```

Enable `YouTube Data API v3` in Google Cloud.

## Neon

This project uses `DATABASE_URL` in `backend/.env`.

The backend normalizes `postgresql://...` to `postgresql+psycopg://...` automatically.

## Storage

Local development defaults to file storage under `backend/storage`.

```env
STORAGE_BACKEND=local
STORAGE_LOCAL_DIR=storage
```

To switch to S3-compatible object storage:

```env
STORAGE_BACKEND=s3
STORAGE_S3_BUCKET=your-bucket
STORAGE_S3_REGION=us-east-1
STORAGE_S3_ENDPOINT_URL=
STORAGE_S3_ACCESS_KEY_ID=
STORAGE_S3_SECRET_ACCESS_KEY=
STORAGE_S3_PREFIX=ai-video-website
```

`STORAGE_S3_ENDPOINT_URL` can be left blank for AWS S3 or set for Cloudflare R2, MinIO, Backblaze B2, etc.

## Upload Behavior

- Immediate upload: leave schedule empty.
- Scheduled publishing: set a future timestamp in the UI.
- Failed uploads: the backend retries automatically and keeps the resumable session URI when possible.
- Manual retry: use the retry button in the publish panel.

## Start Commands

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
cd backend
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe main.py
```

Windows helpers:

- `start_frontend.bat`
- `start_backend.bat`
- `start_all.bat`

## Validation Commands

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Backend:

```bash
cd backend
venv\Scripts\python.exe -m compileall .
venv\Scripts\python.exe -m unittest discover -s tests -v
venv\Scripts\python.exe -c "from database import init_db; init_db(); print('database initialized')"
```
