import asyncio
from video_gen import assemble_video


async def run():
    scenes = [
        {
            "image_path": "tmp/scene_3r5p3qke_0.jpg",
            "audio_path": "tmp/scene_3r5p3qke_0.mp3",
            "duration": 1.8,
            "narration": "Hello world",
        }
    ]
    print("Starting assemble...")
    try:
        await assemble_video(scenes, "test title", "test_session_id")
    except Exception as e:
        print("EXCEPTION:", repr(e))


asyncio.run(run())
