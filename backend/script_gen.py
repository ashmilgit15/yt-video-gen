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
    scene_target = {
        "15s": "3-4 scenes total",
        "30s": "5-7 scenes total",
        "45s": "6-8 scenes total",
        "60s": "7-10 scenes total",
    }.get(duration, "6-8 scenes total")

    prompt = f"""
    You are an elite YouTube Shorts scriptwriter and storyboard artist.
    Create a retention-first vertical short about '{topic}'.

    Style: {style}
    Max total duration: {duration}
    Target pacing: {scene_target}

    Hard rules:
    - Scene 1 must open with a scroll-stopping hook in the first 1-2 seconds.
    - Never start with phrases like 'In this video' or 'Today we're going to'.
    - Each scene should deliver one idea only and feel visually different from the last.
    - All scenes must still belong to one cohesive visual world with consistent style, lighting logic, and color mood.
    - Narration must sound natural with TTS: short clauses, conversational wording, strong rhythm.
    - Keep most narration lines under 14 spoken words.
    - Add a pattern interrupt every 2-3 scenes: contrast, reveal, question, or surprising payoff.
    - End with a crisp CTA that feels earned.
    - Vary the CTA style based on content: curiosity, utility, challenge, identity, or proof-loop.
    - Avoid repeating generic lines like 'Follow for more' unless it is clearly the strongest choice.
    - Keep the CTA short, natural, and under 10 spoken words.

    Break the script down into individual scenes. For each scene, provide:
    - 'scene_number'
    - 'narration'
    - 'image_prompt'

    The image_prompt must describe one cinematic vertical shot only.
    It should include:
    - the subject
    - the action
    - framing / camera angle
    - lighting
    - setting
    - mood
    - one realistic detail that makes the shot feel premium

    The image_prompt must NOT mention:
    - text overlays
    - captions
    - split screens
    - collages
    - UI elements
    - watermarks

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
