import os
import json
import httpx
from pydantic import BaseModel
from typing import List
from google import genai
from google.genai import types

# Load env variables if not handled in main
from dotenv import load_dotenv

load_dotenv()


class Scene(BaseModel):
    scene_number: int
    narration: str
    image_prompt: str


class ScriptResponse(BaseModel):
    title: str
    scenes: List[Scene]


async def generate_script(topic: str, style: str, duration: str) -> dict:
    prompt = f"""
    You are a YouTube Shorts script writer. Write punchy, fast-paced scripts 
    optimized for vertical short-form video about '{topic}'. 
    The style should be {style}.
    Max {duration} total duration. Each scene should be 5-10 seconds. 
    Scene count: 6–10 scenes max (to fit within 60s).
    Use a hook in scene 1 that grabs attention in the first 3 seconds. 
    End with a CTA like 'Follow for more'.
    
    Break the script down into individual scenes. For each scene, provide the 'scene_number', 
    the 'narration' (what the voiceover will say), and an 'image_prompt' (a detailed visual description for an AI image generator).
    The response MUST be a valid JSON object matching the following structure:
    {{
        "title": "A catchy title",
        "scenes": [
            {{
                "scene_number": 1,
                "narration": "Narration text here...",
                "image_prompt": "Image generation prompt here..."
            }}
        ]
    }}
    """

    # Try Gemini first
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ScriptResponse,
                    temperature=0.7,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Gemini API failed: {e}. Falling back to OpenRouter...")

    # Fallback to OpenRouter
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise Exception("No valid API key available for Gemini or OpenRouter.")

    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {
                "role": "system",
                "content": "You are a YouTube Shorts script writer. Output valid JSON only, no markdown formatting.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        # Remove markdown if Mistral ignored instructions
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        return json.loads(content)
