from __future__ import annotations

import json
from typing import Any

import httpx

from toon.jobs import Job
from toon.spend import charge

SYSTEM = """You write a short cartoon marketing video as JSON only.
Rules:
- Use only claims present in the brief. Never invent prices, discounts, or statistics.
- Last shot is a call to action.
- Captions are short spoken lines, not paragraphs.
- visual describes the picture. Do not put letters, logos, or captions inside visual.
- One speaker per shot. An argument is alternating shots.
- motion is "hold" unless the brief tier is "animated", then at most 4 shots may be "i2v".
- Sum of seconds must be close to the requested duration.
Return this shape:
{"title":"","characters":[{"id":"hero","name":"","look":"","voice":"alloy"}],"shots":[{"visual":"","speaker":"hero","line":"","caption":"","seconds":4,"motion":"hold"}]}
voice must be one of alloy, echo, fable, onyx, nova, shimmer.
"""


class StoryError(RuntimeError):
    pass


def _size(aspect: str) -> tuple[int, int]:
    if aspect == "16:9":
        return 1280, 720
    return 720, 1280


def validate(data: Any, brief: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise StoryError("story was not an object")
    characters = data.get("characters")
    shots = data.get("shots")
    if not isinstance(characters, list) or not characters:
        raise StoryError("story needs at least one character")
    if not isinstance(shots, list) or not shots:
        raise StoryError("story needs at least one shot")
    ids = []
    voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    for character in characters:
        cid = str(character.get("id") or "").strip()
        if not cid or cid in ids:
            raise StoryError("each character needs a unique id")
        ids.append(cid)
        if character.get("voice") not in voices:
            character["voice"] = "alloy"
        character["look"] = str(character.get("look") or "").strip()
        character["name"] = str(character.get("name") or cid).strip()
    animated = brief.get("tier") == "animated"
    i2v = 0
    duration = int(brief.get("duration") or 30)
    for shot in shots:
        if shot.get("speaker") not in ids:
            shot["speaker"] = ids[0]
        shot["visual"] = str(shot.get("visual") or "").strip()
        shot["line"] = str(shot.get("line") or "").strip()
        shot["caption"] = str(shot.get("caption") or shot["line"]).strip()[:90]
        try:
            shot["seconds"] = max(2, min(8, int(shot.get("seconds") or 4)))
        except (TypeError, ValueError):
            shot["seconds"] = 4
        motion = shot.get("motion")
        if animated and motion == "i2v" and i2v < 4:
            shot["motion"] = "i2v"
            i2v += 1
            shot["seconds"] = min(shot["seconds"], 4)
        else:
            shot["motion"] = "hold"
        if not shot["visual"]:
            raise StoryError("every shot needs a visual")
    data["title"] = str(data.get("title") or "Untitled")[:80]
    data["aspect"] = brief.get("aspect") if brief.get("aspect") in {"9:16", "16:9"} else "9:16"
    data["size"] = {"width": _size(data["aspect"])[0], "height": _size(data["aspect"])[1]}
    data["duration"] = duration
    return data


def _complete(job: Job, messages: list[dict[str, str]]) -> str:
    key = job.settings.openai_api_key
    if not key:
        raise StoryError("OPENAI_API_KEY is not set. Add it to .env and restart.")
    charge(job, "story", note="script")
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": job.settings.openai_model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": messages,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise StoryError(f"story model failed ({response.status_code})")
    return response.json()["choices"][0]["message"]["content"]


def write_story(job: Job, vision_note: str = "") -> dict[str, Any]:
    if job.exists("story.json"):
        return job.read_json("story.json")
    brief = job.read_json("brief.json")
    user = {
        "description": brief.get("description", ""),
        "aspect": brief.get("aspect", "9:16"),
        "duration": brief.get("duration", 30),
        "tier": brief.get("tier", "still"),
        "image_note": vision_note,
    }
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(user)},
    ]
    last_error = "invalid story"
    for _ in range(2):
        raw = _complete(job, messages)
        try:
            data = validate(json.loads(raw), brief)
        except (json.JSONDecodeError, StoryError) as exc:
            last_error = str(exc)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Invalid: {last_error}. Return corrected JSON only."})
            continue
        job.write_json("story.json", data)
        return data
    raise StoryError(last_error)
