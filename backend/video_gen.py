import asyncio
import os
import re
import subprocess

from ffmpeg_utils import FFMPEG


BASE_DIR = os.path.dirname(__file__)
TMP_DIR = os.path.join(BASE_DIR, "tmp")
TRANSITION_DURATION = 0.16
THUMBNAIL_VARIANTS = [
    ("headline", "Headline Hook"),
    ("clean", "Clean Focus"),
    ("badge", "Number Badge"),
    ("highlight", "Highlight Overlay"),
]


def _normalize_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace(",", r"\,")
        .replace("%", r"\%")
        .replace("[", r"\[")
        .replace("]", r"\]")
    )


def _short_overlay_text(text: str, max_words: int = 7) -> str:
    words = re.sub(r"\s+", " ", (text or "")).strip().split()
    return " ".join(words[:max_words]).upper() or "WATCH THIS"


def _wrap_title_lines(
    text: str, words_per_line: int = 4, max_lines: int = 2
) -> list[str]:
    words = re.sub(r"\s+", " ", (text or "")).strip().split()
    if not words:
        return ["WATCH THIS"]

    lines = [
        " ".join(words[i : i + words_per_line]).upper()
        for i in range(0, min(len(words), words_per_line * max_lines), words_per_line)
    ]
    return lines[:max_lines]


def _caption_chunks(narration: str) -> list[str]:
    words = narration.split()
    if not words:
        return []

    chunk_size = 3 if len(words) > 8 else 2
    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        current.append(word)
        if len(current) >= chunk_size or word.endswith((".", "!", "?", ",")):
            chunks.append(" ".join(current))
            current = []

    if current:
        chunks.append(" ".join(current))

    return chunks


def _script_text(title: str, scenes: list[dict]) -> str:
    narration = " ".join(scene.get("narration", "") for scene in scenes)
    return f"{title} {narration}".lower()


def _music_mood(title: str, scenes: list[dict]) -> str:
    text = _script_text(title, scenes)
    if any(
        word in text
        for word in ["warning", "danger", "scam", "shocking", "secret", "myth"]
    ):
        return "urgent"
    if any(word in text for word in ["history", "ancient", "empire", "war", "legend"]):
        return "dramatic"
    if any(
        word in text
        for word in ["code", "python", "ai", "tool", "automation", "tutorial"]
    ):
        return "technical"
    if any(
        word in text for word in ["meditation", "health", "calm", "peace", "healing"]
    ):
        return "calm"
    if any(
        word in text for word in ["success", "motivation", "habit", "growth", "improve"]
    ):
        return "uplifting"
    if any(word in text for word in ["funny", "weird", "crazy", "wild", "strange"]):
        return "playful"
    if any(word in text for word in ["why", "how", "what", "fact", "discover"]):
        return "curious"
    return "curious"


def _music_profile(session_id: str, mood: str) -> dict[str, float | int]:
    roots = {
        "urgent": [110, 123, 147],
        "dramatic": [98, 110, 131],
        "technical": [123, 147, 165],
        "calm": [98, 110, 123],
        "uplifting": [131, 147, 165],
        "playful": [147, 165, 196],
        "curious": [110, 131, 147],
    }
    root_choices = roots.get(mood, roots["curious"])
    index = sum(ord(char) for char in session_id) % len(root_choices)
    root = root_choices[index]

    profiles = {
        "urgent": {
            "root": root,
            "fifth": int(root * 1.5),
            "noise_amp": 0.02,
            "pulse": 0.05,
            "echo": 0.10,
            "bed_volume": 0.16,
        },
        "dramatic": {
            "root": root,
            "fifth": int(root * 1.5),
            "noise_amp": 0.017,
            "pulse": 0.045,
            "echo": 0.14,
            "bed_volume": 0.18,
        },
        "technical": {
            "root": root,
            "fifth": int(root * 1.333),
            "noise_amp": 0.013,
            "pulse": 0.03,
            "echo": 0.08,
            "bed_volume": 0.16,
        },
        "calm": {
            "root": root,
            "fifth": int(root * 1.5),
            "noise_amp": 0.011,
            "pulse": 0.022,
            "echo": 0.16,
            "bed_volume": 0.14,
        },
        "uplifting": {
            "root": root,
            "fifth": int(root * 1.5),
            "noise_amp": 0.014,
            "pulse": 0.038,
            "echo": 0.12,
            "bed_volume": 0.17,
        },
        "playful": {
            "root": root,
            "fifth": int(root * 1.5),
            "noise_amp": 0.012,
            "pulse": 0.04,
            "echo": 0.09,
            "bed_volume": 0.17,
        },
        "curious": {
            "root": root,
            "fifth": int(root * 1.5),
            "noise_amp": 0.015,
            "pulse": 0.032,
            "echo": 0.12,
            "bed_volume": 0.17,
        },
    }
    return profiles.get(mood, profiles["curious"])


def _cta_text(title: str, scenes: list[dict], session_id: str) -> str:
    text = _script_text(title, scenes)
    cta_groups = []
    if any(
        word in text for word in ["how", "step", "tool", "python", "ai", "tutorial"]
    ):
        cta_groups.append(["SAVE THIS PLAYBOOK", "TEST THIS TODAY", "USE THIS NEXT"])
    if any(
        word in text for word in ["fact", "history", "mind-blowing", "weird", "unknown"]
    ):
        cta_groups.append(["PART 2 NEXT?", "MORE FACTS NEXT", "WANT THE NEXT 5?"])
    if any(word in text for word in ["warning", "mistake", "scam", "avoid"]):
        cta_groups.append(["DON'T MISS PART 2", "SAVE THIS NOW", "CHECK YOURS NEXT"])
    if any(word in text for word in ["motivation", "habit", "success", "growth"]):
        cta_groups.append(
            ["FOLLOW THIS SERIES", "TRY THIS TONIGHT", "BUILD THIS HABIT"]
        )
    if not cta_groups:
        cta_groups.append(
            ["FOLLOW FOR MORE", "WANT THE NEXT ONE?", "MORE LIKE THIS NEXT"]
        )

    options = [option for group in cta_groups for option in group]
    index = sum(ord(char) for char in session_id) % len(options)
    return options[index]


def _cutaway_phrase(narration: str) -> str | None:
    matches = re.findall(r"\b\d+[\w%+]*\b", narration)
    if matches:
        return matches[0].upper()

    for keyword in [
        "largest",
        "smallest",
        "first",
        "secret",
        "ancient",
        "shocking",
        "hidden",
        "never",
        "why",
        "because",
    ]:
        if re.search(rf"\b{keyword}\b", narration, flags=re.IGNORECASE):
            return keyword.upper()

    words = re.findall(r"[A-Za-z']+", narration)
    if not words:
        return None
    return " ".join(word.upper() for word in words[:2])


def _interrupt_phrase(scene_index: int, narration: str) -> str | None:
    if scene_index == 0:
        return None

    lowered = narration.lower()
    if "?" in narration:
        return "BUT WHY?"
    if any(word in lowered for word in ["secret", "hidden", "unknown"]):
        return "HIDDEN FACT"
    if any(word in lowered for word in ["largest", "biggest", "most"]):
        return "MIND-BLOWING"

    phrases = ["WAIT FOR IT", "HERE'S WHY", "REAL TWIST", "LOOK CLOSER"]
    return phrases[scene_index % len(phrases)]


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


async def create_music_bed(duration: float, session_id: str, mood: str) -> str:
    output_path = os.path.join(TMP_DIR, f"music_bed_{session_id}.wav")
    fade_out_start = max(duration - 1.4, 0.0)
    profile = _music_profile(session_id, mood)
    root = int(profile["root"])
    fifth = int(profile["fifth"])
    noise_amp = float(profile["noise_amp"])
    pulse = float(profile["pulse"])
    echo = float(profile["echo"])

    await run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            f"anoisesrc=color=pink:sample_rate=48000:amplitude={noise_amp}",
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            f"sine=f={root}:sample_rate=48000",
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            f"sine=f={fifth}:sample_rate=48000",
            "-filter_complex",
            (
                "[0:a]lowpass=f=1200,highpass=f=80,volume=0.75[n];"
                f"[1:a]volume={pulse}[s1];"
                f"[2:a]volume={pulse * 0.62:.3f}[s2];"
                "[n][s1][s2]amix=inputs=3:duration=longest:normalize=0,"
                f"aecho=0.7:0.35:45:{echo:.2f},"
                f"afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.2f}:d=1.4,"
                "loudnorm=I=-31:TP=-2:LRA=7[aout]"
            ),
            "-map",
            "[aout]",
            "-c:a",
            "pcm_s16le",
            output_path,
        ]
    )

    return output_path


async def render_final_video(
    clip_paths: list[str],
    clip_durations: list[float],
    session_id: str,
    title: str,
    scenes: list[dict],
    final_output: str,
) -> None:
    transition_duration = min(TRANSITION_DURATION, min(clip_durations) / 4)
    total_duration = sum(clip_durations) - transition_duration * max(
        len(clip_paths) - 1, 0
    )
    mood = _music_mood(title, scenes)
    print(f"Using music mood '{mood}' for session {session_id}")
    music_bed = await create_music_bed(total_duration, session_id, mood)

    args = ["-y"]
    for clip_path in clip_paths:
        args.extend(["-i", clip_path])
    args.extend(["-i", music_bed])

    filter_parts: list[str] = []
    for index in range(len(clip_paths)):
        filter_parts.append(f"[{index}:v]settb=AVTB[v{index}]")
        filter_parts.append(f"[{index}:a]aresample=48000[a{index}]")

    video_label = "v0"
    audio_label = "a0"
    current_duration = clip_durations[0]

    for index in range(1, len(clip_paths)):
        next_video_label = f"vxf{index}"
        next_audio_label = f"axf{index}"
        offset = max(current_duration - transition_duration, 0.0)
        transition = "fadeblack" if index % 3 == 0 else "fade"
        filter_parts.append(
            f"[{video_label}][v{index}]xfade=transition={transition}:duration={transition_duration:.2f}:offset={offset:.2f}[{next_video_label}]"
        )
        filter_parts.append(
            f"[{audio_label}][a{index}]acrossfade=d={transition_duration:.2f}:c1=tri:c2=tri[{next_audio_label}]"
        )
        video_label = next_video_label
        audio_label = next_audio_label
        current_duration = (
            current_duration + clip_durations[index] - transition_duration
        )

    bed_index = len(clip_paths)
    bed_fade_out = max(current_duration - 1.4, 0.0)
    bed_volume = float(_music_profile(session_id, mood)["bed_volume"])
    filter_parts.append(
        f"[{bed_index}:a]volume={bed_volume:.2f},lowpass=f=1400,highpass=f=70,afade=t=in:st=0:d=1.0,afade=t=out:st={bed_fade_out:.2f}:d=1.4[bed]"
    )
    filter_parts.append(
        f"[{audio_label}][bed]amix=inputs=2:weights='1 0.22':normalize=0,alimiter=limit=0.96[aout]"
    )

    args.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            f"[{video_label}]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            final_output,
        ]
    )

    print(f"Running final assembly for session {session_id}")
    await run_ffmpeg(args)


def _build_motion_filter(scene_index: int, frames: int, fps: int) -> str:
    mode = scene_index % 4
    zoom_expr = "min(zoom+0.0012,1.18)"

    if mode == 0:
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = "(ih-ih/zoom)*0.34"
    elif mode == 1:
        x_expr = f"(iw-iw/zoom)*(1-on/{frames})"
        y_expr = "(ih-ih/zoom)*0.56"
    elif mode == 2:
        x_expr = "(iw-iw/zoom)*0.48"
        y_expr = f"(ih-ih/zoom)*on/{frames}"
    else:
        x_expr = "(iw-iw/zoom)*0.52"
        y_expr = f"(ih-ih/zoom)*(1-on/{frames})"

    return (
        "scale=1800:3200:force_original_aspect_ratio=increase,"
        "crop=1800:3200,"
        f"zoompan=z='{zoom_expr}':d={frames}:"
        f"x='{x_expr}':y='{y_expr}':s=1080x1920:fps={fps}"
    )


def _build_subtitle_filters(narration: str, duration: float) -> list[str]:
    chunks = _caption_chunks(narration)
    if not chunks:
        return []

    chunk_duration = duration / len(chunks)
    filters: list[str] = [
        "drawbox=x=54:y=ih*0.71:w=iw-108:h=236:color=black@0.30:t=fill",
        "drawbox=x=54:y=ih*0.71:w=iw-108:h=12:color=0x8b5cf6@0.95:t=fill",
    ]

    for index, chunk in enumerate(chunks):
        start_time = index * chunk_duration
        end_time = (index + 1) * chunk_duration
        safe_chunk = _escape_drawtext(chunk.upper())
        words = chunk.split()
        filters.append(
            "drawtext="
            f"text='{safe_chunk}':"
            "fontsize=68:fontcolor=white:borderw=4:bordercolor=black@0.70:"
            "shadowx=0:shadowy=4:shadowcolor=black@0.55:"
            "x=(w-text_w)/2:y=h*0.79:"
            f"enable='between(t,{start_time:.2f},{end_time:.2f})'"
        )

        if words:
            word_duration = max(chunk_duration / len(words), 0.08)
            for word_index, word in enumerate(words):
                word_start = start_time + word_index * word_duration
                word_end = min(end_time, word_start + word_duration)
                safe_word = _escape_drawtext(word.upper())
                filters.append(
                    "drawtext="
                    f"text='{safe_word}':"
                    "fontsize=78:fontcolor=0xfacc15:borderw=4:bordercolor=black@0.85:"
                    "shadowx=0:shadowy=3:shadowcolor=black@0.60:"
                    "x=(w-text_w)/2:y=h*0.72:"
                    f"enable='between(t,{word_start:.2f},{word_end:.2f})'"
                )

    return filters


def _build_scene_overlay_filters(
    title: str,
    narration: str,
    cta_text: str,
    scene_index: int,
    total_scenes: int,
    duration: float,
    is_last_scene: bool,
) -> list[str]:
    progress = (scene_index + 1) / max(total_scenes, 1)
    title_lines = [_escape_drawtext(line) for line in _wrap_title_lines(title)]
    filters: list[str] = [
        "drawbox=x=70:y=82:w=iw-140:h=10:color=white@0.12:t=fill",
        f"drawbox=x=70:y=82:w=(iw-140)*{progress:.4f}:h=10:color=0x22c55e@0.98:t=fill",
        (
            "drawtext="
            f"text='SCENE {scene_index + 1:02d} / {total_scenes:02d}':"
            "fontsize=34:fontcolor=white@0.92:borderw=2:bordercolor=black@0.60:"
            "x=70:y=102"
        ),
    ]

    if scene_index == 0:
        filters.extend(
            [
                "drawbox=x=70:y=140:w=iw-140:h=220:color=black@0.22:t=fill:enable='between(t,0,1.7)'",
                (
                    "drawtext="
                    "text='SCROLL-STOPPING FACTS':"
                    "fontsize=32:fontcolor=0xfacc15:borderw=2:bordercolor=black@0.55:"
                    "x=(w-text_w)/2:y=164:"
                    "enable='between(t,0.08,1.7)'"
                ),
            ]
        )
        for line_index, line in enumerate(title_lines):
            filters.append(
                "drawtext="
                f"text='{line}':"
                "fontsize=74:fontcolor=white:borderw=4:bordercolor=black@0.65:"
                f"x=(w-text_w)/2:y={218 + line_index * 74}:"
                "enable='between(t,0,1.7)'"
            )

    interrupt_phrase = _interrupt_phrase(scene_index, narration)
    if scene_index > 0 and not is_last_scene and interrupt_phrase:
        interrupt_start = min(max(duration * 0.32, 0.55), max(duration - 0.65, 0.55))
        interrupt_end = min(duration - 0.08, interrupt_start + 0.52)
        safe_interrupt = _escape_drawtext(interrupt_phrase)
        filters.extend(
            [
                (
                    "drawbox=x=(iw-540)/2:y=156:w=540:h=90:color=0xef4444@0.90:t=fill:"
                    f"enable='between(t,{interrupt_start:.2f},{interrupt_end:.2f})'"
                ),
                (
                    "drawtext="
                    f"text='{safe_interrupt}':"
                    "fontsize=42:fontcolor=white:borderw=3:bordercolor=black@0.55:"
                    "x=(w-text_w)/2:y=183:"
                    f"enable='between(t,{interrupt_start:.2f},{interrupt_end:.2f})'"
                ),
            ]
        )

    cutaway_phrase = _cutaway_phrase(narration)
    if scene_index > 0 and cutaway_phrase and duration >= 2.2:
        cutaway_start = min(max(duration * 0.52, 0.9), max(duration - 0.9, 0.9))
        cutaway_end = min(duration - 0.12, cutaway_start + 0.45)
        safe_cutaway = _escape_drawtext(cutaway_phrase)
        filters.extend(
            [
                (
                    "drawbox=x=90:y=ih*0.58:w=440:h=92:color=black@0.58:t=fill:"
                    f"enable='between(t,{cutaway_start:.2f},{cutaway_end:.2f})'"
                ),
                (
                    "drawtext="
                    f"text='{safe_cutaway}':"
                    "fontsize=46:fontcolor=0xf8fafc:borderw=3:bordercolor=black@0.55:"
                    "x=122:y=h*0.605:"
                    f"enable='between(t,{cutaway_start:.2f},{cutaway_end:.2f})'"
                ),
            ]
        )

    if is_last_scene:
        safe_cta = _escape_drawtext(cta_text)
        cta_start = max(duration - 1.35, 0.0)
        filters.extend(
            [
                (
                    "drawbox=x=120:y=190:w=iw-240:h=112:color=0x7c3aed@0.92:t=fill:"
                    f"enable='between(t,{cta_start:.2f},{duration:.2f})'"
                ),
                (
                    "drawtext="
                    f"text='{safe_cta}':"
                    "fontsize=48:fontcolor=white:borderw=3:bordercolor=black@0.55:"
                    "x=(w-text_w)/2:y=222:"
                    f"enable='between(t,{cta_start:.2f},{duration:.2f})'"
                ),
            ]
        )

    return filters


def _thumbnail_filters(title: str, variant: str) -> list[str]:
    title_lines = [_escape_drawtext(line) for line in _wrap_title_lines(title, 4, 2)]
    base_filters = [
        "scale=1600:2844:force_original_aspect_ratio=increase,crop=1080:1920",
        "eq=saturation=1.10:contrast=1.08:brightness=0.01",
    ]

    if variant == "clean":
        return [
            *base_filters,
            "crop=980:1740:50:120",
            "scale=1080:1920",
            "drawbox=x=70:y=120:w=16:h=420:color=0x22c55e@0.95:t=fill",
            "drawbox=x=120:y=160:w=620:h=110:color=black@0.20:t=fill",
            "drawtext=text='CLEAN LOOK':fontsize=42:fontcolor=white:borderw=2:bordercolor=black@0.4:x=148:y=195",
        ]

    if variant == "badge":
        filters = [
            *base_filters,
            "drawbox=x=70:y=120:w=120:h=430:color=0xf59e0b@0.96:t=fill",
            "drawbox=x=170:y=190:w=800:h=310:color=black@0.24:t=fill",
            "drawbox=x=170:y=540:w=280:h=108:color=0xef4444@0.95:t=fill",
            "drawtext=text='TOP 5':fontsize=48:fontcolor=white:borderw=2:bordercolor=black@0.45:x=220:y=573",
        ]
        for line_index, line in enumerate(title_lines):
            filters.append(
                "drawtext="
                f"text='{line}':"
                "fontsize=82:fontcolor=white:borderw=4:bordercolor=black@0.65:"
                f"x=192:y={280 + line_index * 92}"
            )
        return filters

    if variant == "highlight":
        filters = [
            *base_filters,
            "drawbox=x=58:y=108:w=964:h=520:color=black@0.14:t=4",
            "drawbox=x=70:y=120:w=120:h=430:color=0x8b5cf6@0.96:t=fill",
            "drawbox=x=170:y=190:w=820:h=310:color=black@0.28:t=fill",
            "drawbox=x=150:y=850:w=760:h=130:color=black@0.22:t=fill",
            "drawtext=text='LOOK CLOSER':fontsize=44:fontcolor=0xfacc15:borderw=2:bordercolor=black@0.45:x=360:y=888",
        ]
        for line_index, line in enumerate(title_lines):
            filters.append(
                "drawtext="
                f"text='{line}':"
                "fontsize=80:fontcolor=white:borderw=4:bordercolor=black@0.65:"
                f"x=192:y={280 + line_index * 92}"
            )
        return filters

    filters = [
        *base_filters,
        "drawbox=x=70:y=120:w=120:h=430:color=0x8b5cf6@0.96:t=fill",
        "drawbox=x=170:y=190:w=800:h=310:color=black@0.24:t=fill",
        "drawtext=text='WATCH THIS':fontsize=34:fontcolor=0xfacc15:borderw=2:bordercolor=black@0.45:x=192:y=214",
    ]
    for line_index, line in enumerate(title_lines):
        filters.append(
            "drawtext="
            f"text='{line}':"
            "fontsize=84:fontcolor=white:borderw=4:bordercolor=black@0.65:"
            f"x=192:y={280 + line_index * 92}"
        )
    filters.extend(
        [
            "drawbox=x=170:y=540:w=420:h=96:color=0x22c55e@0.95:t=fill",
            "drawtext=text='HIGH RETENTION SHORT':fontsize=36:fontcolor=white:borderw=2:bordercolor=black@0.45:x=202:y=570",
        ]
    )
    return filters


async def create_thumbnail_variant(
    image_path: str, title: str, session_id: str, variant: str
) -> str:
    image_path = _normalize_path(image_path)
    output_path = os.path.join(TMP_DIR, f"thumbnail_{session_id}_{variant}.jpg")
    filters = _thumbnail_filters(title, variant)

    await run_ffmpeg(
        [
            "-y",
            "-i",
            image_path,
            "-vf",
            ",".join(filters),
            "-frames:v",
            "1",
            output_path,
        ]
    )

    return output_path


async def create_thumbnail(image_path: str, title: str, session_id: str) -> str:
    return await create_thumbnail_variant(image_path, title, session_id, "headline")


async def create_thumbnail_variants(
    image_path: str, title: str, session_id: str
) -> list[dict[str, str]]:
    variants = []
    for variant_name, variant_label in THUMBNAIL_VARIANTS:
        path = await create_thumbnail_variant(
            image_path, title, session_id, variant_name
        )
        variants.append({"name": variant_name, "label": variant_label, "path": path})
    return variants


async def extract_thumbnail_frame(video_path: str, session_id: str) -> str:
    video_path = _normalize_path(video_path)
    output_path = os.path.join(TMP_DIR, f"thumbnail_source_{session_id}.jpg")
    await run_ffmpeg(
        [
            "-y",
            "-ss",
            "0.20",
            "-i",
            video_path,
            "-frames:v",
            "1",
            output_path,
        ]
    )
    return output_path


async def create_thumbnail_variants_from_video(
    video_path: str, title: str, session_id: str
) -> list[dict[str, str]]:
    source_frame = await extract_thumbnail_frame(video_path, session_id)
    return await create_thumbnail_variants(source_frame, title, session_id)


async def create_scene_clip(
    image_path: str,
    audio_path: str,
    duration: float,
    narration: str,
    scene_index: int,
    total_scenes: int,
    title: str,
    cta_text: str,
    is_last_scene: bool,
    output_path: str,
) -> None:
    image_path = _normalize_path(image_path)
    audio_path = _normalize_path(audio_path)
    output_path = _normalize_path(output_path)

    fps = 30
    frames = max(1, int(duration * fps))
    fade_in_duration = min(0.18, max(duration / 6, 0.08))
    fade_out_duration = min(0.22, max(duration / 6, 0.10))
    fade_out_start = max(duration - fade_out_duration, 0.0)

    filter_chain = ",".join(
        [
            _build_motion_filter(scene_index, frames, fps),
            "eq=saturation=1.08:contrast=1.05:brightness=0.015",
            f"fade=t=in:st=0:d={fade_in_duration:.2f}",
            f"fade=t=out:st={fade_out_start:.2f}:d={fade_out_duration:.2f}",
            *_build_scene_overlay_filters(
                title,
                narration,
                cta_text,
                scene_index,
                total_scenes,
                duration,
                is_last_scene,
            ),
            *_build_subtitle_filters(narration, duration),
        ]
    )

    audio_filter = ",".join(
        [
            "highpass=f=110",
            "lowpass=f=7500",
            "acompressor=threshold=-18dB:ratio=2.2:attack=20:release=180:makeup=3",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            f"afade=t=in:st=0:d={fade_in_duration:.2f}",
            f"afade=t=out:st={fade_out_start:.2f}:d={fade_out_duration:.2f}",
        ]
    )

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
        "-af",
        audio_filter,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        "-t",
        str(duration),
        "-shortest",
        output_path,
    ]

    print(f"Running ffmpeg for scene {scene_index}")
    await run_ffmpeg(args)


async def assemble_video(scenes: list, title: str, session_id: str) -> str:
    os.makedirs(TMP_DIR, exist_ok=True)

    selected_scenes: list[dict] = []
    total_duration = 0.0

    for index, scene in enumerate(scenes):
        duration = float(scene["duration"])
        if total_duration + duration > 60.0:
            print(f"Truncating at scene {index} to fit within 60s limit.")
            break
        selected_scenes.append(scene)
        total_duration += duration

    if not selected_scenes:
        raise RuntimeError("No scene clips were generated.")

    clip_paths: list[str] = []
    clip_durations: list[float] = []
    total_scenes = len(selected_scenes)
    cta_text = _cta_text(title, selected_scenes, session_id)

    for index, scene in enumerate(selected_scenes):
        clip_path = os.path.join(TMP_DIR, f"clip_{session_id}_{index}.mp4")
        await create_scene_clip(
            scene["image_path"],
            scene["audio_path"],
            float(scene["duration"]),
            scene["narration"],
            index,
            total_scenes,
            title,
            cta_text,
            index == total_scenes - 1,
            clip_path,
        )
        clip_paths.append(clip_path)
        clip_durations.append(float(scene["duration"]))

    list_file = os.path.join(TMP_DIR, f"concat_{session_id}.txt")
    with open(list_file, "w", encoding="utf-8") as file_handle:
        for clip_path in clip_paths:
            file_handle.write(f"file '{clip_path.replace(chr(92), '/')}'\n")

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower() or "shorts"
    final_output = os.path.join(TMP_DIR, f"shorts_{slug}_{session_id}.mp4")

    await render_final_video(
        clip_paths, clip_durations, session_id, title, selected_scenes, final_output
    )

    return final_output
