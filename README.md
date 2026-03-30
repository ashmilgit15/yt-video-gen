# AI Shorts Generator

Turn a topic into a short vertical video, connect multiple YouTube accounts, and upload the final Short with AI-generated title, description, and tags.

## What This Project Does

This app helps you:

- sign in with Clerk
- generate a Shorts script with AI
- turn the script into images, audio, and a final MP4
- connect multiple YouTube accounts with Google OAuth
- upload one Short to multiple channels
- optionally schedule publishing on YouTube
- retry failed uploads automatically and manually

## Built With

### Frontend

- React
- Vite
- Clerk
- Axios
- Tailwind CSS

### Backend

- FastAPI
- SQLAlchemy
- Neon Postgres
- Google OAuth + YouTube Data API
- FFmpeg

## Project Structure

```text
AI-video-website/
├─ frontend/        # React + Vite app
├─ backend/         # FastAPI API, video generation, auth, uploads
├─ start_frontend.bat
├─ start_backend.bat
├─ start_all.bat
├─ DEVELOPMENT.md   # more detailed setup notes
└─ README.md
```

## Main Features

- Clerk authentication for the app
- Google OAuth for connecting YouTube channels
- Multiple YouTube accounts per user
- AI-generated upload metadata
- Scheduled publishing
- Upload retry/resume support
- Neon database storage for users, videos, channels, and uploads
- Local storage for development, S3-compatible storage support for production

## Beginner-Friendly Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/ashmilgit15/yt-video-gen.git
cd yt-video-gen
```

### 2. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on:

```text
http://localhost:5173
```

### 3. Start the backend

Open a second terminal:

```bash
cd backend
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe main.py
```

The backend runs on:

```text
http://localhost:8000
```

### 4. Or use the Windows helper scripts

From the project root:

```text
start_frontend.bat
start_backend.bat
start_all.bat
```

## Environment Variables

### Frontend

Create `frontend/.env.local`:

```env
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
VITE_API_BASE_URL=http://localhost:8000
```

### Backend

Create `backend/.env`:

```env
DATABASE_URL=your_neon_connection_string
FRONTEND_URL=http://localhost:5173

CLERK_SECRET_KEY=your_clerk_secret_key
CLERK_AUTHORIZED_PARTIES=http://localhost:5173

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/youtube/connect/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=your_fernet_key

GEMINI_API_KEY=your_gemini_key
OPENROUTER_API_KEY=your_openrouter_key
POLLINATIONS_API_KEY=your_pollinations_key
DEFAULT_TTS=edge

STORAGE_BACKEND=local
STORAGE_LOCAL_DIR=storage
```

You can also copy from:

- `frontend/.env.example`
- `backend/.env.example`

## Google OAuth Setup

In Google Cloud Console, use these for local development:

Authorized JavaScript origin:

```text
http://localhost:5173
```

Authorized redirect URI:

```text
http://localhost:8000/youtube/connect/callback
```

## How The Flow Works

1. User signs in with Clerk.
2. User generates a script.
3. User reviews or edits the script.
4. Backend renders the Short.
5. User connects one or more YouTube accounts.
6. User selects channels and uploads the Short.
7. Backend generates metadata and publishes or schedules the upload.

## Validation Commands

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

### Backend

```bash
cd backend
venv\Scripts\python.exe -m compileall .
venv\Scripts\python.exe -m unittest discover -s tests -v
venv\Scripts\python.exe -c "from database import init_db; init_db(); print('database initialized')"
```

## Notes

- `backend/.env` and `frontend/.env.local` are ignored and should not be committed.
- Local development uses file storage.
- Production can use any S3-compatible object storage.
- FFmpeg must be available for video rendering.

## Extra Docs

If you want a more detailed setup walkthrough, read:

```text
DEVELOPMENT.md
```
