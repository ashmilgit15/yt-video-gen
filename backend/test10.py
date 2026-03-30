import asyncio
import video_gen
import os


async def mk():
    scenes = [
        {
            "image_path": os.path.abspath("tmp/scene_3r5p3qke_0.jpg"),
            "audio_path": os.path.abspath("tmp/scene_3r5p3qke_0.mp3"),
            "duration": 5.0,
            "narration": "Imagine a place where gravity is so strong, nothing, not even light, can escape!",
        }
    ]
    await video_gen.assemble_video(scenes, "Test", "test")


asyncio.run(mk())
