import asyncio
import os
import re
import subprocess

from ffmpeg_utils import FFMPEG


BASE_DIR = os.path.dirname(__file__)
TMP_DIR = os.path.join(BASE_DIR, "tmp")


def _normalize_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


async def run_ffmpeg(args: list[str]) -> tuple[bytes, bytes]:
    cmd = [FFMPEG] + args

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=BASE_DIR,
        )

    process = await asyncio.to_thread(_run)
    if process.returncode != 0:
        error_msg = process.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"FFmpeg failed (code {process.returncode}):\n{error_msg}")
    return process.stdout, process.stderr


def _build_subtitle_filters(narration: str, duration: float) -> list[str]:
    words = narration.split()
    if not words:
        return []

    chunks = [" ".join(words[i : i + 4]) for i in range(0, len(words), 4)]
    chunk_duration = duration / len(chunks)
    filters: list[str] = []

    for index, chunk in enumerate(chunks):
        start_time = index * chunk_duration
        end_time = (index + 1) * chunk_duration
        safe_chunk = (
            chunk.replace("\\", r"\\")
            .replace("'", "\u2019")
            .replace(":", r"\:")
            .replace(",", r"\,")
            .replace("%", r"\%")
        )
        filters.append(
            "drawtext="
            f"text='{safe_chunk}':"
            "fontsize=60:fontcolor=white:borderw=3:bordercolor=black:"
            "x=(w-text_w)/2:y=h*0.75:"
            f"enable='between(t,{start_time},{end_time})'"
        )

    return filters


async def create_scene_clip(
    image_path: str,
    audio_path: str,
    duration: float,
    narration: str,
    scene_index: int,
    output_path: str,
) -> None:
    image_path = _normalize_path(image_path)
    audio_path = _normalize_path(audio_path)
    output_path = _normalize_path(output_path)

    fps = 25
    frames = max(1, int(duration * fps))
    zoom_expr = (
        f"scale=3000:-1,zoompan=z='min(zoom+0.002,1.5)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps}"
        if scene_index % 2 == 0
        else f"scale=3000:-1,zoompan=z='max(1.5-0.002*in,1.0)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps}"
    )

    filter_chain = ",".join([zoom_expr, *_build_subtitle_filters(narration, duration)])
    args = [
        "-y",
        "-loop",
        "1",
        "-i",
        image_path,
        "-i",
        audio_path,
        "-vf",
        filter_chain,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        str(duration),
        "-shortest",
        output_path,
    ]

    print(f"Running ffmpeg for scene {scene_index}")
    await run_ffmpeg(args)


async def assemble_video(scenes: list, title: str, session_id: str) -> str:
    os.makedirs(TMP_DIR, exist_ok=True)

    clip_paths: list[str] = []
    total_duration = 0.0

    for index, scene in enumerate(scenes):
        duration = float(scene["duration"])
        if total_duration + duration > 60.0:
            print(f"Truncating at scene {index} to fit within 60s limit.")
            break

        clip_path = os.path.join(TMP_DIR, f"clip_{session_id}_{index}.mp4")
        await create_scene_clip(
            scene["image_path"],
            scene["audio_path"],
            duration,
            scene["narration"],
            index,
            clip_path,
        )
        clip_paths.append(clip_path)
        total_duration += duration

    if not clip_paths:
        raise RuntimeError("No scene clips were generated.")

    list_file = os.path.join(TMP_DIR, f"concat_{session_id}.txt")
    with open(list_file, "w", encoding="utf-8") as file_handle:
        for clip_path in clip_paths:
            file_handle.write(f"file '{clip_path.replace(chr(92), '/')}'\n")

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower() or "shorts"
    final_output = os.path.join(TMP_DIR, f"shorts_{slug}_{session_id}.mp4")

    print(f"Running concat for session {session_id}")
    await run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c",
            "copy",
            final_output,
        ]
    )

    return final_output
