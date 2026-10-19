from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx

from toon.jobs import Job
from toon.spend import charge

STYLE = (
    "Flat cartoon, thick clean outlines, limited bright palette, "
    "simple shapes, no text, no letters, no watermark, no logo."
)


class ProviderError(RuntimeError):
    pass


def _openai_headers(job: Job) -> dict[str, str]:
    if not job.settings.openai_api_key:
        raise ProviderError("OPENAI_API_KEY is not set. Add it to .env and restart.")
    return {"Authorization": f"Bearer {job.settings.openai_api_key}"}


def draw(job: Job, prompt: str, dest: Path, size: str) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    charge(job, "image", note=dest.name)
    if job.settings.image_backend == "fal":
        _fal_image(job, prompt, dest)
        return
    if job.settings.image_backend != "openai":
        raise ProviderError("No image key set. Add OPENAI_API_KEY or FAL_KEY to .env.")
    response = httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers=_openai_headers(job),
        json={
            "model": job.settings.openai_image_model,
            "prompt": f"{STYLE} {prompt}",
            "size": size,
            "n": 1,
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise ProviderError(f"image generation failed ({response.status_code})")
    body = response.json()["data"][0]
    if body.get("b64_json"):
        dest.write_bytes(base64.b64decode(body["b64_json"]))
        return
    image = httpx.get(body["url"], timeout=60)
    image.raise_for_status()
    dest.write_bytes(image.content)


def speak(job: Job, text: str, voice: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    if not text.strip():
        return
    charge(job, "tts", note=dest.name)
    if job.settings.speech_backend == "elevenlabs":
        voice_id = job.settings.elevenlabs_voice_id
        if not voice_id:
            raise ProviderError("ELEVENLABS_VOICE_ID is not set.")
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": job.settings.elevenlabs_api_key},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
            timeout=60,
        )
    else:
        if job.settings.speech_backend != "openai":
            raise ProviderError("No speech key set. Add OPENAI_API_KEY to .env.")
        response = httpx.post(
            "https://api.openai.com/v1/audio/speech",
            headers=_openai_headers(job),
            json={"model": "tts-1", "voice": voice or "alloy", "input": text},
            timeout=60,
        )
    if response.status_code >= 400:
        raise ProviderError(f"speech failed ({response.status_code})")
    dest.write_bytes(response.content)


def animate(job: Job, image: Path, prompt: str, seconds: int, dest: Path) -> bool:
    """Return True if a video clip was written. False means caller should Ken Burns."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    if not job.settings.animation_enabled:
        return False
    charge(job, "i2v_second", units=min(seconds, 4), note=dest.name)
    payload = _fal_queue(
        job,
        job.settings.video_model,
        {
            "prompt": prompt,
            "image_url": _as_data_url(image),
            "start_image_url": _as_data_url(image),
            "duration": str(min(seconds, 4)),
        },
    )
    url = _first_url(payload)
    if not url:
        raise ProviderError("video model returned no file")
    video = httpx.get(url, timeout=120)
    video.raise_for_status()
    dest.write_bytes(video.content)
    return True


def lipsync(job: Job, video: Path, audio: Path, dest: Path, seconds: int) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    if not (job.settings.fal_key and job.settings.lipsync_model):
        return False
    charge(job, "lipsync_second", units=seconds, note=dest.name)
    payload = _fal_queue(
        job,
        job.settings.lipsync_model,
        {"video_url": _as_data_url(video), "audio_url": _as_data_url(audio)},
    )
    url = _first_url(payload)
    if not url:
        return False
    result = httpx.get(url, timeout=120)
    result.raise_for_status()
    dest.write_bytes(result.content)
    return True


def _as_data_url(path: Path) -> str:
    mime = "video/mp4" if path.suffix == ".mp4" else "image/png"
    if path.suffix == ".mp3":
        mime = "audio/mpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _fal_image(job: Job, prompt: str, dest: Path) -> None:
    payload = _fal_queue(job, job.settings.image_model, {"prompt": f"{STYLE} {prompt}"})
    url = _first_url(payload)
    if not url:
        raise ProviderError("image model returned no file")
    image = httpx.get(url, timeout=60)
    image.raise_for_status()
    dest.write_bytes(image.content)


def _fal_queue(job: Job, model: str, arguments: dict) -> dict:
    submit = httpx.post(
        f"https://queue.fal.run/{model}",
        headers={"Authorization": f"Key {job.settings.fal_key}"},
        json=arguments,
        timeout=60,
    )
    if submit.status_code >= 400:
        raise ProviderError(f"{model} rejected the request ({submit.status_code})")
    body = submit.json()
    status_url = body.get("status_url")
    response_url = body.get("response_url")
    if not status_url or not response_url:
        return body
    headers = {"Authorization": f"Key {job.settings.fal_key}"}
    for _ in range(90):
        status = httpx.get(status_url, headers=headers, timeout=30)
        status.raise_for_status()
        state = status.json().get("status")
        if state == "COMPLETED":
            result = httpx.get(response_url, headers=headers, timeout=60)
            result.raise_for_status()
            return result.json()
        if state not in {"IN_QUEUE", "IN_PROGRESS"}:
            raise ProviderError(f"{model} failed: {state}")
        time.sleep(2)
    raise ProviderError(f"{model} timed out")


def _first_url(payload: dict) -> str:
    if isinstance(payload.get("images"), list) and payload["images"]:
        return payload["images"][0].get("url", "")
    video = payload.get("video")
    if isinstance(video, dict):
        return video.get("url", "")
    if isinstance(payload.get("url"), str):
        return payload["url"]
    return ""
