import asyncio
import subprocess
from ffmpeg_utils import FFMPEG


async def mk():
    def _run():
        return subprocess.run(
            [
                FFMPEG,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=1080x1920:d=1",
                "-vf",
                "drawtext=text='Hello':fontsize=60:fontcolor=white:x=100:y=100",
                "tmp/test_drawtext.mp4",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    process = await asyncio.to_thread(_run)
    print("CODE", process.returncode)
    print("ERR", process.stderr.decode("utf-8", errors="replace"))


asyncio.run(mk())
