import os
import aiofiles
import httpx
import asyncio
from urllib.parse import quote
import random
import time
import subprocess
import re
from dotenv import load_dotenv
from config import settings
from ffmpeg_utils import FFMPEG

load_dotenv()

_pollinations_lock = asyncio.Lock()
_last_pollinations_request_at = 0.0


def _format_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return repr(exc)


def _simplify_prompt(prompt: str) -> str:
    cleaned = " ".join((prompt or "").split())
    cleaned = re.sub(r"(?i)text overlay:[^,.!?;]*", "", cleaned)
    cleaned = re.sub(
        r"(?i)\b(vertical video|vertical composition|portrait orientation|9:16 aspect ratio|no horizontal letterboxing|fast-paced edit)\b",
        "",
        cleaned,
    )
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    summary = ", ".join(parts[:3]) if parts else cleaned
    summary = re.sub(r"\s+", " ", summary).strip(" ,.-")
    words = summary.split()
    concise = " ".join(words[:20]).strip()
    return concise or "cinematic portrait"


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("%", r"\%")
    )


def _placeholder_copy(prompt: str | None) -> tuple[str, str]:
    simplified = _simplify_prompt(prompt or "scene visual")
    words = simplified.split()
    headline = " ".join(words[:4]).upper() or "SCENE VISUAL"
    subtitle = " ".join(words[4:12]) or "Styled fallback visual"
    return _escape_drawtext(headline), _escape_drawtext(subtitle)


async def _wait_for_pollinations_slot() -> None:
    global _last_pollinations_request_at

    async with _pollinations_lock:
        now = time.monotonic()
        wait_time = max(
            0.0,
            settings.pollinations_min_interval_seconds
            - (now - _last_pollinations_request_at),
        )
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        _last_pollinations_request_at = time.monotonic()


def _base_headers() -> dict[str, str]:
    return {
        "User-Agent": "AI-Video-Website/1.0",
        "Referer": settings.pollinations_referrer or settings.frontend_host,
    }


def _build_flux_candidates(
    encoded_prompt: str, api_key: str | None
) -> list[tuple[str, dict[str, str], str]]:
    base_url = (
        "https://gen.pollinations.ai/image/"
        f"{encoded_prompt}?model={settings.pollinations_model}"
    )

    candidates = [(base_url, _base_headers(), "gen-anon")]
    if api_key:
        header_auth = _base_headers()
        header_auth["Authorization"] = f"Bearer {api_key}"
        candidates.insert(0, (base_url, header_auth, "gen-bearer"))
        candidates.append(
            (f"{base_url}&key={api_key}", _base_headers(), "gen-query-key")
        )

    return candidates


async def _create_local_fallback_image(filename: str, prompt: str | None = None) -> str:
    headline, subtitle = _placeholder_copy(prompt)

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=#0f172a:s=1080x1920:d=1",
                "-vf",
                (
                    "drawbox=x=72:y=120:w=20:h=300:color=0x8b5cf6@0.96:t=fill,"
                    "drawbox=x=122:y=210:w=840:h=250:color=black@0.20:t=fill,"
                    f"drawtext=text='{headline}':fontsize=80:fontcolor=white:borderw=4:bordercolor=black@0.55:x=132:y=238,"
                    f"drawtext=text='{subtitle}':fontsize=42:fontcolor=0xe2e8f0:borderw=2:bordercolor=black@0.40:x=132:y=356,"
                    "drawtext=text='AI SHORTS STUDIO':fontsize=34:fontcolor=0xfacc15:borderw=2:bordercolor=black@0.35:x=132:y=146"
                ),
                "-frames:v",
                "1",
                filename,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(__file__),
        )

    process = await asyncio.to_thread(_run)
    if process.returncode != 0:
        error = process.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Local fallback image generation failed: {error}")

    return filename


async def create_black_placeholder_image(
    scene_number: int, session_id: str, prompt: str | None = None
) -> str:
    tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    filename = os.path.join(tmp_dir, f"scene_{session_id}_{scene_number}.jpg")
    return await _create_local_fallback_image(filename, prompt)


async def _download_pollinations_image(
    encoded_prompt: str,
    filename: str,
    timeout: httpx.Timeout,
    api_key: str | None,
) -> str:
    max_retries = settings.image_generation_max_retries
    last_error: Exception | None = None

    for candidate_url, headers, label in _build_flux_candidates(
        encoded_prompt, api_key
    ):
        for attempt in range(max_retries):
            try:
                await _wait_for_pollinations_slot()
                async with httpx.AsyncClient(
                    follow_redirects=True, timeout=timeout, headers=headers
                ) as client:
                    response = await client.get(candidate_url)
                response.raise_for_status()

                content_type = (response.headers.get("Content-Type") or "").lower()
                if not content_type.startswith("image/"):
                    raise RuntimeError(
                        f"Pollinations returned non-image content type: {content_type or 'unknown'}"
                    )

                async with aiofiles.open(filename, "wb") as f:
                    await f.write(response.content)
                return filename
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status == 429 and attempt < max_retries - 1:
                    retry_after = exc.response.headers.get("Retry-After")
                    try:
                        delay = max(float(retry_after), 1.0) if retry_after else 0.0
                    except ValueError:
                        delay = 0.0
                    if delay <= 0:
                        delay = settings.pollinations_min_interval_seconds * (
                            attempt + 1
                        )
                    print(
                        f"Pollinations {label} attempt {attempt + 1} hit rate limits, retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                if status >= 500 and attempt < max_retries - 1:
                    delay = 1.5 * (attempt + 1)
                    print(
                        f"Pollinations {label} attempt {attempt + 1} failed with {status}, retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                print(f"Pollinations {label} failed: {_format_error(exc)}")
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    delay = 1.5 * (attempt + 1)
                    print(
                        f"Pollinations {label} attempt {attempt + 1} failed, retrying in {delay:.1f}s... ({_format_error(exc)})"
                    )
                    await asyncio.sleep(delay)
                    continue
                print(f"Pollinations {label} failed: {_format_error(exc)}")
                break

    if last_error is not None:
        raise last_error
    raise RuntimeError("Pollinations image generation failed.")


async def generate_image(
    prompt: str,
    scene_number: int,
    session_id: str,
    visual_direction: str | None = None,
) -> str:
    """
    Generates an image using Pollinations.ai for a specific scene.
    Returns the path to the saved image.
    """
    fallback_models = ["flux", "turbo", "flux-realism"]
    combined_prompt = prompt
    if visual_direction:
        combined_prompt = f"{prompt}, {visual_direction}"
    cleaned_prompt = _simplify_prompt(combined_prompt)[:300]
    encoded_prompt = quote(cleaned_prompt, safe="")

    api_key = os.getenv("POLLINATIONS_API_KEY")
    referrer = quote("ai-video-website", safe="")

    # Create temp directory if not exists
    tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # We use session_id to group files for a single generation job
    filename = os.path.join(tmp_dir, f"scene_{session_id}_{scene_number}.jpg")

    timeout = httpx.Timeout(
        settings.image_generation_timeout_seconds,
        connect=settings.image_generation_connect_timeout_seconds,
    )
    headers = {
        "User-Agent": "AI-Video-Website/1.0",
        "Referer": settings.pollinations_referrer or settings.frontend_host,
    }

    last_error: Exception | None = None

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, headers=headers
    ) as client:
        for model in fallback_models:
            seed = (
                (sum(ord(char) for char in session_id) * 97) + (scene_number * 131)
            ) % 100000
            if seed == 0:
                seed = random.randint(1, 100000)
            key_query = f"&key={quote(api_key, safe='')}" if api_key else ""
            url = (
                "https://gen.pollinations.ai/image/"
                f"{encoded_prompt}?width={settings.image_generation_width}"
                f"&height={settings.image_generation_height}"
                f"&seed={seed}&model={model}&nologo=true"
                f"&referrer={referrer}{key_query}"
            )

            for attempt in range(1, 4):
                try:
                    await _wait_for_pollinations_slot()
                    response = await client.get(url)
                    response.raise_for_status()

                    async with aiofiles.open(filename, "wb") as f:
                        await f.write(response.content)
                    return filename
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        print(
                            f"Image generation with model {model} attempt {attempt} failed, retrying... ({_format_error(exc)})"
                        )
                        await asyncio.sleep(2 * attempt)
                    else:
                        print(
                            f"Image generation with model {model} failed after 3 attempts: {_format_error(exc)}"
                        )

    raise RuntimeError(
        "Pollinations image generation failed after exhausting all retries for models "
        f"{', '.join(fallback_models)} via gen.pollinations.ai. "
        f"Last error: {_format_error(last_error) if last_error else 'Unknown error.'}"
    ) from last_error
