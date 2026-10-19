import json
from pathlib import Path

import pytest

from toon.settings import Settings
from toon.story import StoryError, validate


def settings(tmp_path: Path) -> Settings:
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


def test_validate_forces_hold_and_cta_shape():
    brief = {"aspect": "9:16", "duration": 30, "tier": "still"}
    raw = {
        "title": "Share",
        "characters": [{"id": "bot", "name": "Bot", "look": "small blue robot", "voice": "nope"}],
        "shots": [
            {"visual": "Bot holds a gear", "speaker": "bot", "line": "This is mine.", "caption": "Mine", "seconds": 4, "motion": "i2v"},
            {"visual": "Bot offers the gear", "speaker": "missing", "line": "You can have it.", "seconds": 99, "motion": "i2v"},
        ],
    }
    story = validate(raw, brief)
    assert story["characters"][0]["voice"] == "alloy"
    assert story["shots"][0]["motion"] == "hold"
    assert story["shots"][1]["speaker"] == "bot"
    assert story["shots"][1]["seconds"] == 8
    assert story["size"] == {"width": 720, "height": 1280}


def test_validate_caps_animated_shots():
    brief = {"aspect": "16:9", "duration": 30, "tier": "animated"}
    shots = [
        {"visual": f"scene {i}", "speaker": "bot", "line": "hi", "seconds": 6, "motion": "i2v"}
        for i in range(6)
    ]
    story = validate(
        {"title": "T", "characters": [{"id": "bot", "name": "Bot", "look": "robot", "voice": "nova"}], "shots": shots},
        brief,
    )
    assert sum(shot["motion"] == "i2v" for shot in story["shots"]) == 4
    assert all(shot["seconds"] <= 4 for shot in story["shots"] if shot["motion"] == "i2v")


def test_validate_rejects_empty():
    with pytest.raises(StoryError):
        validate({"characters": [], "shots": []}, {"tier": "still"})


def test_resume_skips_existing_story(tmp_path: Path):
    from toon.jobs import Job

    job = Job.create(settings(tmp_path), {"description": "robot", "aspect": "9:16", "duration": 15, "tier": "still"})
    job.write_json("story.json", {"title": "kept"})
    assert job.exists("story.json")
    again = Job.open(settings(tmp_path), job.id)
    assert again.read_json("story.json")["title"] == "kept"
    assert json.loads((again.root / "meta.json").read_text(encoding="utf-8"))["ai_generated"] is True
