import os
import asyncio
import httpx
import edge_tts
import soundfile as sf
from typing import Tuple
from dotenv import load_dotenv
from ffmpeg_utils import FFPROBE

load_dotenv()

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
KOKORO_MODEL = os.path.join(MODEL_DIR, "kokoro-v0_19.onnx")
KOKORO_VOICES = os.path.join(MODEL_DIR, "voices.json")

# KOKORO_URL_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files"
# The above URL might be different. If it fails, we fall back to edge-tts.
KOKORO_AVAILABLE = False
try:
    from kokoro_onnx import Kokoro

    KOKORO_AVAILABLE = True
except ImportError:
    pass


async def download_file(url: str, dest: str):
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)


async def ensure_kokoro_models():
    os.makedirs(MODEL_DIR, exist_ok=True)
    if not os.path.exists(KOKORO_MODEL):
        print(f"Downloading Kokoro model to {KOKORO_MODEL}...")
        try:
            # We use huggingface to get the model reliably
            await download_file(
                "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v0_19.onnx?download=true",
                KOKORO_MODEL,
            )
        except Exception as e:
            print(f"Failed to download Kokoro model: {e}")
            return False

    if not os.path.exists(KOKORO_VOICES):
        print(f"Downloading Kokoro voices to {KOKORO_VOICES}...")
        try:
            await download_file(
                "https://raw.githubusercontent.com/thewh1teagle/kokoro-onnx/main/voices.json",
                KOKORO_VOICES,
            )
        except Exception as e:
            print(f"Failed to download Kokoro voices: {e}")
            return False

    return True


_kokoro_instance = None


def get_kokoro():
    global _kokoro_instance
    if _kokoro_instance is None:
        _kokoro_instance = Kokoro(KOKORO_MODEL, KOKORO_VOICES)
    return _kokoro_instance


import random


async def get_audio_duration(audio_path: str, text: str) -> float:
    if FFPROBE is None:
        return max(1.0, len(text) / 15.0)
    try:
        import subprocess

        def _run():
            return subprocess.run(
                [
                    FFPROBE,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.path.dirname(__file__),
            )

        process = await asyncio.to_thread(_run)
        return float(process.stdout.decode().strip())
    except Exception:
        return max(1.0, len(text) / 15.0)


async def generate_audio_edge(
    text: str, filename: str, voice: str
) -> Tuple[str, float]:
    """Fallback using edge-tts with retries"""
    print(f"Generating audio with Edge TTS for {filename}...")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Add small random jitter to prevent hitting rate limits perfectly concurrently
            await asyncio.sleep(random.uniform(0.1, 1.0))
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filename)
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Edge TTS failed after {max_retries} attempts: {e}")
                raise e
            print(f"Edge TTS attempt {attempt + 1} failed, retrying... ({e})")
            await asyncio.sleep(1.0)

    duration = await get_audio_duration(filename, text)
    return filename, duration


async def generate_audio(
    text: str, scene_number: int, session_id: str, voice: str
) -> dict:
    tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    filename = os.path.join(tmp_dir, f"scene_{session_id}_{scene_number}")

    default_tts = os.getenv("DEFAULT_TTS", "kokoro").lower()

    # Map friendly names to actual voice IDs
    voice_map_kokoro = {
        "bella": "af_bella",
        "sarah": "af_sarah",
        "aria": "af_bella",  # Aria is edge-tts only, map to bella for kokoro
    }

    voice_map_edge = {
        "bella": "en-US-JennyNeural",
        "sarah": "en-US-AriaNeural",
        "aria": "en-US-AriaNeural",
    }

    if default_tts == "kokoro" and KOKORO_AVAILABLE:
        kokoro_ready = await ensure_kokoro_models()
        if kokoro_ready:
            try:
                kokoro_voice = voice_map_kokoro.get(voice.lower(), "af_bella")
                print(f"Generating audio with Kokoro for {filename}.wav...")
                kokoro = get_kokoro()

                # Kokoro generation
                samples, sample_rate = kokoro.create(
                    text, voice=kokoro_voice, speed=1.0, lang="en-us"
                )
                wav_filename = f"{filename}.wav"
                sf.write(wav_filename, samples, sample_rate)

                # Get duration
                duration = len(samples) / sample_rate
                return {"path": wav_filename, "duration": duration}

            except Exception as e:
                print(f"Kokoro generation failed: {e}. Falling back to Edge TTS.")

    # Edge TTS fallback
    mp3_filename = f"{filename}.mp3"
    edge_voice = voice_map_edge.get(voice.lower(), "en-US-AriaNeural")
    path, duration = await generate_audio_edge(text, mp3_filename, edge_voice)
    return {"path": path, "duration": duration}
