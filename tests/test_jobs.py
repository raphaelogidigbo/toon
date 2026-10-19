from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from toon.jobs import Job
from toon.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        openai_api_key="",
        openai_model="gpt-4o-mini",
        openai_image_model="gpt-image-1",
        fal_key="",
        image_model="",
        video_model="",
        lipsync_model="",
        tts_provider="openai",
        elevenlabs_api_key="",
        elevenlabs_voice_id="",
        max_usd_per_job=3,
        root=tmp_path,
        output_dir=tmp_path / "output",
    )


def test_invalid_job_id(tmp_path: Path):
    with pytest.raises(ValueError):
        Job(_settings(tmp_path), "../macabots")


def test_second_run_keeps_files(tmp_path: Path):
    job = Job.create(_settings(tmp_path), {"description": "a robot", "tier": "still"})
    target = job.root / "frames" / "01.png"
    target.write_bytes(b"png")
    opened = Job.open(_settings(tmp_path), job.id)
    assert opened.exists("frames/01.png")
    assert opened.path("frames/01.png").read_bytes() == b"png"


def test_health_and_empty_description(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("FAL_KEY", "")
    import app as app_module

    app_module.settings = _settings(tmp_path)
    client = TestClient(app_module.app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["animation"] is False
    denied = client.post("/api/jobs", data={"description": "   "})
    assert denied.status_code == 400
