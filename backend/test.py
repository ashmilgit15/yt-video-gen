import asyncio


async def test():
    p = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=100x100:d=1",
        "/tmp/test.mp4",
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await p.communicate()
    print("RETURN CODE", p.returncode)
    print("ERR", err.decode())


asyncio.run(test())
