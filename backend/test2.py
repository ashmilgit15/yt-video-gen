import asyncio


async def mk():
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=1080x1920:d=1",
        "-vframes",
        "1",
        "/tmp/test.jpg",
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    print(err.decode())


asyncio.run(mk())
