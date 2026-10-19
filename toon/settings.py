from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
if not os.getenv("OPENAI_API_KEY", "").strip():
    local = Path.home() / ".codeium" / "windsurf" / "toon.env"
    if local.is_file():
        load_dotenv(local)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_image_model: str
    fal_key: str
    image_model: str
    video_model: str
    lipsync_model: str
    tts_provider: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    max_usd_per_job: float
    root: Path
    output_dir: Path
    access_code: str = ""

    @property
    def animation_enabled(self) -> bool:
        return bool(self.fal_key and self.video_model)

    @property
    def image_backend(self) -> str:
        if self.fal_key:
            return "fal"
        if self.openai_api_key:
            return "openai"
        return ""

    @property
    def speech_backend(self) -> str:
        if self.tts_provider == "elevenlabs" and self.elevenlabs_api_key:
            return "elevenlabs"
        if self.openai_api_key:
            return "openai"
        return ""


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1",
        fal_key=os.getenv("FAL_KEY", "").strip(),
        image_model=os.getenv("IMAGE_MODEL", "fal-ai/flux/dev").strip() or "fal-ai/flux/dev",
        video_model=os.getenv("VIDEO_MODEL", "").strip(),
        lipsync_model=os.getenv("LIPSYNC_MODEL", "").strip(),
        tts_provider=os.getenv("TTS_PROVIDER", "openai").strip().lower() or "openai",
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
        elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "").strip(),
        max_usd_per_job=_float("MAX_USD_PER_JOB", 3.0),
        access_code=os.getenv("ACCESS_CODE", "").strip(),
        root=ROOT,
        output_dir=ROOT / "output",
    )
