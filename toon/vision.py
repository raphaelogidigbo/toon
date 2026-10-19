from __future__ import annotations

import base64
from pathlib import Path

import httpx

from toon.jobs import Job


def describe_upload(job: Job) -> str:
    if job.exists("vision.json"):
        return job.read_json("vision.json").get("text", "")
    upload = next(job.root.glob("upload.*"), None)
    if upload is None:
        return ""
    key = job.settings.openai_api_key
    if not key:
        note = "User supplied an image. Use it as the first frame. Do not redraw it."
        job.write_json("vision.json", {"text": note})
        return note
    encoded = base64.b64encode(upload.read_bytes()).decode("ascii")
    mime = "image/png" if upload.suffix.lower() == ".png" else "image/jpeg"
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": job.settings.openai_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this image for a storyboard. Extract any visible text separately. JSON: {\"description\":\"\",\"text\":\"\"}",
                        },
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()["choices"][0]["message"]["content"]
    job.write_json("vision.json", {"raw": payload, "file": upload.name})
    text = payload
    try:
        import json

        parsed = json.loads(payload)
        text = f"{parsed.get('description', '')}\nVisible text: {parsed.get('text', '')}".strip()
        job.write_json("vision.json", {"text": text, "file": upload.name})
    except json.JSONDecodeError:
        job.write_json("vision.json", {"text": text, "file": upload.name})
    return text


def upload_path(job: Job) -> Path | None:
    return next(job.root.glob("upload.*"), None)
