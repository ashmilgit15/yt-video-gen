import asyncio
import subprocess
from ffmpeg_utils import FFMPEG


async def mk():
    zoom_filter = "scale=3000:-1,zoompan=z='min(zoom+0.002,1.5)':d=45:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=25"
    all_filters = (
        zoom_filter
        + ",drawtext=text='Hello':fontsize=60:fontcolor=white:borderw=3:bordercolor=black:x=(w-text_w)/2:y=h*0.75:enable='between(t,0,1.8)'"
    )

    def _run():
        return subprocess.run(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=1080x1920:d=2",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono:d=2",  # dummy audio
                "-vf",
                all_filters,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-t",
                "1.8",
                "-shortest",
                "tmp/test_clip.mp4",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    process = await asyncio.to_thread(_run)
    print("CODE", process.returncode)
    print("ERR", process.stderr.decode("utf-8", errors="replace"))


asyncio.run(mk())
