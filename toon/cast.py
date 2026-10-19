from __future__ import annotations

from toon.jobs import Job
from toon.providers import draw


def build_cast(job: Job) -> None:
    story = job.read_json("story.json")
    width = story["size"]["width"]
    height = story["size"]["height"]
    size = f"{width}x{height}"
    for character in story["characters"]:
        dest = job.root / "cast" / f"{character['id']}.png"
        prompt = (
            f"Character sheet of {character['name']}, {character['look']}. "
            "Front view, plain background, full figure, same outfit, readable face."
        )
        draw(job, prompt, dest, size)
