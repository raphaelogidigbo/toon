"""Zero-cost end-to-end check of the ffmpeg stages (speech/motion/assemble)."""
from __future__ import annotations

import sys

from PIL import Image, ImageDraw

from toon.assemble import assemble, ffmpeg_available
from toon.jobs import Job
from toon.motion import build_motion
from toon.settings import load_settings
from toon.speech import build_speech

assert ffmpeg_available(), "ffmpeg not found"

settings = load_settings()
job = Job.create(settings, {"description": "smoke test", "aspect": "9:16", "duration": 8, "tier": "still"})
print("job:", job.root)

job.write_json(
    "story.json",
    {
        "title": "Smoke",
        "aspect": "9:16",
        "size": {"width": 720, "height": 1280},
        "characters": [{"id": "hero", "name": "Hero", "look": "robot", "voice": "alloy"}],
        "shots": [
            {"visual": "shot one", "speaker": "hero", "line": "", "caption": "Caption one", "seconds": 3, "motion": "hold"},
            {"visual": "shot two", "speaker": "hero", "line": "", "caption": "Caption two", "seconds": 3, "motion": "hold"},
        ],
    },
)

for index, color in enumerate(((200, 80, 40), (60, 120, 200)), start=1):
    img = Image.new("RGB", (720, 1280), color)
    ImageDraw.Draw(img).ellipse((160, 460, 560, 860), fill=(245, 240, 230))
    img.save(job.root / "frames" / f"{index:02d}.png")

build_speech(job)
assert job.exists("captions.srt"), "captions.srt missing"
print("speech ok ->", (job.root / "captions.srt").read_text().replace("\n", " | "))

build_motion(job)
for name in ("01.mp4", "02.mp4"):
    clip = job.root / "clips" / name
    assert clip.stat().st_size > 10_000, f"{name} too small"
print("motion ok ->", [p.name for p in (job.root / "clips").iterdir()])

assemble(job)
final = job.root / "final.mp4"
assert final.stat().st_size > 10_000, "final.mp4 too small"
print("assemble ok -> final.mp4", final.stat().st_size, "bytes")
print("PASS")
sys.exit(0)
