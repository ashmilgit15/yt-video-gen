import json
import os
import re
from typing import List

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from dotenv import load_dotenv


load_dotenv()


CATEGORY_LABELS = {
    "22": "People & Blogs",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "17": "Sports",
}


CLICKBAIT_WORDS = {
    "shocking",
    "insane",
    "unbelievable",
    "must watch",
    "jaw-dropping",
}


class UploadMetadataResponse(BaseModel):
    title: str
    description: str
    tags: List[str] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)
    title_variants: List[str] = Field(default_factory=list)
    category_id: str = "22"
    suggested_privacy_status: str = "private"
    suggested_publish_mode: str = "scheduled"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _topic_tokens(topic: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z0-9+#]+", (topic or ""))
        if len(token) >= 3
    ]


def _is_timely(topic: str, title: str, script: dict) -> bool:
    haystack = f"{topic} {title} {' '.join(scene.get('narration', '') for scene in script.get('scenes') or [])}".lower()
    return any(
        keyword in haystack
        for keyword in [
            "today",
            "latest",
            "breaking",
            "update",
            "election",
            "budget",
            "this week",
            "this year",
            "news",
        ]
    )


def _infer_category(topic: str, style: str) -> tuple[str, str]:
    topic_lower = (topic or "").lower()
    style_lower = (style or "").lower()

    if any(
        token in topic_lower
        for token in ["python", "coding", "programming", "ai", "software", "tech"]
    ):
        return "28", CATEGORY_LABELS["28"]
    if any(
        token in topic_lower for token in ["workout", "fitness", "sports", "training"]
    ):
        return "17", CATEGORY_LABELS["17"]
    if any(
        token in topic_lower for token in ["news", "politics", "election", "government"]
    ):
        return "25", CATEGORY_LABELS["25"]
    if "tutorial" in style_lower:
        return "26", CATEGORY_LABELS["26"]
    if any(
        token in style_lower for token in ["educational", "myth", "fact", "history"]
    ):
        return "27", CATEGORY_LABELS["27"]
    if any(token in style_lower for token in ["story", "motivational"]):
        return "22", CATEGORY_LABELS["22"]
    return "22", CATEGORY_LABELS["22"]


def _infer_upload_strategy(
    topic: str, style: str, title: str, script: dict
) -> tuple[str, str]:
    if _is_timely(topic, title, script):
        return "public", "public"

    style_lower = (style or "").lower()
    if any(
        token in style_lower
        for token in ["tutorial", "educational", "myth", "motivational", "story"]
    ):
        return "private", "scheduled"

    return "private", "scheduled"


def _build_hashtags(topic: str, style: str) -> list[str]:
    hashtags: list[str] = []
    style_map = {
        "educational": "#Education",
        "tutorial": "#Tutorial",
        "story": "#Storytime",
        "myth": "#MythBusting",
        "motivational": "#SelfImprovement",
        "listicle": "#Facts",
    }

    topic_tokens = _topic_tokens(topic)
    if topic_tokens:
        hashtags.append(f"#{re.sub(r'[^A-Za-z0-9]', '', topic_tokens[0].title())}")

    style_lower = (style or "").lower()
    for key, hashtag in style_map.items():
        if key in style_lower:
            hashtags.append(hashtag)
            break

    if any(
        token in topic.lower()
        for token in ["python", "ai", "history", "fitness", "finance"]
    ):
        topic_map = {
            "python": "#Python",
            "ai": "#AI",
            "history": "#History",
            "fitness": "#Fitness",
            "finance": "#Finance",
        }
        for key, hashtag in topic_map.items():
            if key in topic.lower():
                hashtags.append(hashtag)
                break

    return _dedupe(hashtags)[:3]


def _build_tags(raw_tags: list, topic: str, style: str) -> list[str]:
    aliases: list[str] = []
    topic_lower = (topic or "").lower()
    alias_map = {
        "chatgpt": ["chat gpt", "openai", "ai writing"],
        "ai": ["artificial intelligence"],
        "python": ["python programming", "python tutorial"],
        "youtube": ["youtube shorts"],
    }
    for key, values in alias_map.items():
        if key in topic_lower:
            aliases.extend(values)

    base = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    base.extend(_topic_tokens(topic)[:3])
    if style:
        base.append(style)
    base.extend(aliases)
    return _dedupe(base)[:5]


def _sanitize_title(title: str, fallback_title: str, topic: str) -> str:
    cleaned = re.sub(
        r"\s+", " ", (title or fallback_title or topic or "AI Shorts")
    ).strip()
    cleaned = re.sub(r"[!?]{2,}", "!", cleaned)
    for phrase in CLICKBAIT_WORDS:
        if phrase in cleaned.lower():
            cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE).strip(
                " -:!?"
            )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()
    weak_tail_words = {"you", "your", "this", "that", "these", "those", "must"}
    if len(words) < 4 or (words and words[-1].lower() in weak_tail_words):
        cleaned = fallback_title or topic or cleaned
    if len(cleaned) > 70:
        cleaned = cleaned[:70].rsplit(" ", 1)[0].strip()
    return cleaned[:100] or (fallback_title[:100] if fallback_title else "AI Shorts")


def _finalize_description(
    description: str, hashtags: list[str], fallback_title: str
) -> str:
    cleaned = (description or fallback_title or "").strip()
    if not cleaned:
        cleaned = "Watch this AI-generated YouTube Short."

    if hashtags:
        hashtag_block = " ".join(hashtags[:3])
        if hashtag_block not in cleaned:
            cleaned = f"{cleaned}\n\n{hashtag_block}".strip()

    return cleaned[:5000]


def _duration_seconds(duration: str) -> int:
    match = re.search(r"(\d+)", duration or "")
    return int(match.group(1)) if match else 30


def _script_words(script: dict) -> list[str]:
    text = " ".join(scene.get("narration", "") for scene in script.get("scenes") or [])
    return re.findall(r"[A-Za-z']+", text)


def _build_title_variants(
    base_title: str, topic: str, style: str, script: dict
) -> list[dict]:
    scene_count = len(script.get("scenes") or [])
    topic_clean = re.sub(r"\s+", " ", topic).strip() or "This Topic"
    base_title = _sanitize_title(base_title, base_title, topic)
    title_forms = [
        (base_title, "clear"),
    ]

    style_lower = (style or "").lower()
    if any(token in style_lower for token in ["tutorial", "howto", "how-to"]):
        title_forms.extend(
            [
                (f"Save time with {topic_clean}", "tutorial"),
                (f"{topic_clean}: a faster workflow", "specific"),
            ]
        )
    elif any(token in style_lower for token in ["story", "motivational"]):
        title_forms.extend(
            [
                (f"What happened when {topic_clean}", "story"),
                (f"The shift that changed {topic_clean}", "curiosity"),
            ]
        )
    else:
        title_forms.extend(
            [
                (f"Why {topic_clean} matters more than you think", "curiosity"),
                (f"{scene_count} reasons {topic_clean} stands out", "specific"),
            ]
        )

    variants: list[dict] = []
    seen: set[str] = set()
    for raw_title, angle in title_forms:
        title = _sanitize_title(raw_title, base_title, topic)
        lowered = title.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        score = 50
        if len(title) <= 60:
            score += 10
        if _topic_tokens(topic) and any(
            token.lower() in title.lower() for token in _topic_tokens(topic)[:2]
        ):
            score += 15
        if any(char.isdigit() for char in title):
            score += 8
        if title.endswith("?"):
            score += 5
        if len(title.split()) <= 10:
            score += 7
        variants.append({"title": title, "angle": angle, "score": min(score, 100)})

    return variants[:3]


def _retention_report(title: str, style: str, duration: str, script: dict) -> dict:
    scenes = script.get("scenes") or []
    first_line = (scenes[0].get("narration") if scenes else "") or ""
    last_line = (scenes[-1].get("narration") if scenes else "") or ""
    words = _script_words(script)
    total_words = len(words)
    duration_seconds = max(_duration_seconds(duration), 1)
    words_per_second = total_words / duration_seconds
    avg_words_per_scene = total_words / max(len(scenes), 1)

    hook_words = ["why", "how", "secret", "never", "hidden", "truth", "fact", "mistake"]
    payoff_words = ["because", "so", "which means", "the reason", "reveals"]
    escalation_words = ["but", "then", "next", "until", "finally", "suddenly"]
    filler_words = ["basically", "actually", "literally", "kind of", "sort of"]

    hook_strength = 8
    if any(word in first_line.lower() for word in hook_words) or "?" in first_line:
        hook_strength += 8
    if len(first_line.split()) <= 12:
        hook_strength += 4

    payoff_speed = 8
    if any(word in first_line.lower() for word in payoff_words) or any(
        word in (scenes[1].get("narration", "").lower() if len(scenes) > 1 else "")
        for word in payoff_words
    ):
        payoff_speed += 5
    if len(scenes) >= 5:
        payoff_speed += 2

    beat_density = min(15, max(6, int((len(scenes) / max(duration_seconds, 1)) * 80)))

    filler_count = sum(1 for word in filler_words if word in " ".join(words).lower())
    script_tightness = 15
    if avg_words_per_scene > 16:
        script_tightness -= 4
    if words_per_second > 3.4:
        script_tightness -= 3
    script_tightness -= min(4, filler_count)

    curiosity = 4
    if any(word in " ".join(words).lower() for word in hook_words):
        curiosity += 3
    if "?" in first_line or "?" in title:
        curiosity += 3

    escalation = 4 + min(
        6, sum(1 for word in escalation_words if word in " ".join(words).lower())
    )
    edit_energy = min(10, 5 + len(scenes) // 2)
    ending = 2
    if any(word in last_line.lower() for word in ["follow", "save", "part 2", "next"]):
        ending += 3

    overall = max(
        0,
        min(
            100,
            hook_strength
            + payoff_speed
            + beat_density
            + script_tightness
            + curiosity
            + escalation
            + edit_energy
            + ending,
        ),
    )

    flags: list[str] = []
    if hook_strength < 12:
        flags.append("Hook may be too soft in the first 2 seconds")
    if payoff_speed < 10:
        flags.append("Value payoff could land earlier")
    if beat_density < 10:
        flags.append("More visual or semantic beats may improve retention")
    if script_tightness < 11:
        flags.append("Narration may be too dense or wordy")
    if ending < 4:
        flags.append("Ending CTA/payoff could be stronger")

    return {
        "overall_score": overall,
        "breakdown": {
            "hook_strength": hook_strength,
            "payoff_speed": payoff_speed,
            "beat_density": beat_density,
            "script_tightness": script_tightness,
            "curiosity": curiosity,
            "escalation": escalation,
            "edit_energy": edit_energy,
            "ending_strength": ending,
        },
        "flags": flags,
    }


def _normalize_metadata(
    payload: dict,
    fallback_title: str,
    topic: str,
    style: str,
    duration: str,
    script: dict,
) -> dict:
    category_id, category_label = _infer_category(topic, style)
    suggested_privacy_status, suggested_publish_mode = _infer_upload_strategy(
        topic,
        style,
        payload.get("title") or fallback_title,
        script,
    )

    hashtags = _build_hashtags(topic, style)
    generated_hashtags = payload.get("hashtags") or []
    hashtags = _dedupe([*generated_hashtags, *hashtags])[:3]

    primary_title = _sanitize_title(
        payload.get("title") or fallback_title, fallback_title, topic
    )
    title_variants = _build_title_variants(primary_title, topic, style, script)
    generated_variants = payload.get("title_variants") or []
    for candidate in generated_variants:
        title = _sanitize_title(candidate, fallback_title, topic)
        if not any(
            existing["title"].lower() == title.lower() for existing in title_variants
        ):
            title_variants.append({"title": title, "angle": "generated", "score": 72})
    title_variants = title_variants[:3]

    return {
        "title": primary_title,
        "description": _finalize_description(
            payload.get("description") or "", hashtags, fallback_title
        ),
        "tags": _build_tags(payload.get("tags") or [], topic, style),
        "hashtags": hashtags,
        "title_variants": title_variants,
        "retention_report": _retention_report(primary_title, style, duration, script),
        "category_id": str(payload.get("category_id") or category_id),
        "category_label": category_label,
        "suggested_privacy_status": payload.get("suggested_privacy_status")
        or suggested_privacy_status,
        "suggested_publish_mode": payload.get("suggested_publish_mode")
        or suggested_publish_mode,
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
    category_id, category_label = _infer_category(topic, style)
    suggested_privacy_status, suggested_publish_mode = _infer_upload_strategy(
        topic, style, fallback_title, script
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
      "title": "Hooky but clear Shorts title",
      "title_variants": ["Variant 1", "Variant 2", "Variant 3"],
      "description": "SEO-friendly description",
      "tags": ["tag1", "tag2"],
      "hashtags": ["#TagOne", "#TagTwo"],
      "category_id": "{category_id}",
      "suggested_privacy_status": "{suggested_privacy_status}",
      "suggested_publish_mode": "{suggested_publish_mode}"
    }}

    Requirements:
    - Generate a title optimized for YouTube Shorts mobile readability.
    - Preferred title length: 35-60 characters. Hard cap: 70 characters.
    - Put the core topic early in the title.
    - Use one clear hook only. Avoid spammy clickbait.
    - Do not use ALL CAPS.
    - Avoid words like shocking, insane, unbelievable, must watch.
    - Description should feel natural, concise, and include 1 short CTA.
    - Use 1-3 hashtags only, usually 2.
    - Tags are only for relevant aliases, misspellings, or niche search terms.
    - Recommended category for this content is {category_label} ({category_id}).
    - Recommended privacy is {suggested_privacy_status}; recommended publish mode is {suggested_publish_mode}.
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
            return _normalize_metadata(
                json.loads(response.text),
                fallback_title,
                topic,
                style,
                duration,
                script,
            )
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
                "tags": [topic],
                "hashtags": _build_hashtags(topic, style),
                "category_id": category_id,
                "suggested_privacy_status": suggested_privacy_status,
                "suggested_publish_mode": suggested_publish_mode,
            },
            fallback_title,
            topic,
            style,
            duration,
            script,
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
        return _normalize_metadata(
            json.loads(content), fallback_title, topic, style, duration, script
        )
