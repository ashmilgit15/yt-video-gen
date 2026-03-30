import json
import os
from typing import List

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel

from dotenv import load_dotenv


load_dotenv()


class UploadMetadataResponse(BaseModel):
    title: str
    description: str
    tags: List[str]
    category_id: str


def _normalize_metadata(payload: dict, fallback_title: str) -> dict:
    title = (payload.get("title") or fallback_title or "AI Shorts").strip()
    description = (payload.get("description") or "").strip()
    raw_tags = payload.get("tags") or []
    tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()][:12]
    category_id = str(payload.get("category_id") or "22")

    return {
        "title": title[:100],
        "description": description[:5000],
        "tags": tags,
        "category_id": category_id,
    }


async def generate_upload_metadata(
    topic: str, style: str, duration: str, script: dict
) -> dict:
    fallback_title = script.get("title") or topic
    scenes = script.get("scenes") or []
    scene_lines = "\n".join(
        f"Scene {scene.get('scene_number', index + 1)}: {scene.get('narration', '')}"
        for index, scene in enumerate(scenes)
    )

    prompt = f"""
    You are creating YouTube Shorts upload metadata for an AI-generated vertical short.

    Topic: {topic}
    Style: {style}
    Target Duration: {duration}
    Script Title: {fallback_title}
    Narration:
    {scene_lines}

    Return valid JSON with this shape only:
    {{
      "title": "Short and compelling title under 100 characters",
      "description": "SEO-friendly YouTube description under 5000 characters",
      "tags": ["tag1", "tag2"],
      "category_id": "22"
    }}

    Requirements:
    - Optimize for YouTube Shorts discovery.
    - Do not use clickbait that misrepresents the video.
    - Tags should be relevant and concise.
    - Description should mention the topic naturally and include a short CTA.
    - Use category_id 22 unless another obvious YouTube category is clearly better.
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=UploadMetadataResponse,
                    temperature=0.7,
                ),
            )
            return _normalize_metadata(json.loads(response.text), fallback_title)
        except Exception as exc:
            print(
                f"Gemini metadata generation failed: {exc}. Falling back to OpenRouter..."
            )

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_key:
        return _normalize_metadata(
            {
                "title": fallback_title,
                "description": f"{fallback_title}\n\nGenerated automatically for YouTube Shorts.",
                "tags": [topic, "shorts", "youtube shorts"],
                "category_id": "22",
            },
            fallback_title,
        )

    headers = {
        "Authorization": f"Bearer {openrouter_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": [
            {
                "role": "system",
                "content": "You create YouTube Shorts metadata. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=45.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        return _normalize_metadata(json.loads(content), fallback_title)
