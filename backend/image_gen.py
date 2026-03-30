import os
import aiofiles
import httpx
import asyncio
from urllib.parse import quote_plus
import random
from dotenv import load_dotenv

load_dotenv()


async def generate_image(prompt: str, scene_number: int, session_id: str) -> str:
    """
    Generates an image using Pollinations.ai for a specific scene.
    Returns the path to the saved image.
    """
    # Append YouTube Shorts specific requirements to the prompt
    enhanced_prompt = f"{prompt}, vertical composition, portrait orientation, centered subject, 9:16 aspect ratio, no horizontal letterboxing"

    encoded_prompt = quote_plus(enhanced_prompt)
    seed = random.randint(1, 100000)

    # Use Flux Schnell as requested
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={seed}&model=flux"

    api_key = os.getenv("POLLINATIONS_API_KEY")
    if api_key:
        url += f"&key={api_key}"

    # Create temp directory if not exists
    tmp_dir = os.path.join(os.path.dirname(__file__), "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    # We use session_id to group files for a single generation job
    filename = os.path.join(tmp_dir, f"scene_{session_id}_{scene_number}.jpg")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Increase timeout for image generation
                response = await client.get(url, timeout=60.0)
                response.raise_for_status()

                async with aiofiles.open(filename, "wb") as f:
                    await f.write(response.content)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Pollinations API failed after {max_retries} attempts: {e}")
                    raise e
                print(
                    f"Image generation attempt {attempt + 1} failed, retrying... ({e})"
                )
                await asyncio.sleep(2.0)

    return filename
