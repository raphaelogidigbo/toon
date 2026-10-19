from __future__ import annotations

import shutil

from toon.jobs import Job
from toon.providers import draw
from toon.vision import upload_path


def build_frames(job: Job) -> None:
    story = job.read_json("story.json")
    size = f"{story['size']['width']}x{story['size']['height']}"
    characters = {item["id"]: item for item in story["characters"]}
    upload = upload_path(job)
    for index, shot in enumerate(story["shots"], start=1):
        dest = job.root / "frames" / f"{index:02d}.png"
        if index == 1 and upload is not None:
            if not dest.exists():
                shutil.copyfile(upload, dest)
            continue
        character = characters.get(shot["speaker"], {})
        look = character.get("look", "")
        prompt = (
            f"Scene: {shot['visual']}. "
            f"The speaker looks like: {look}. "
            "Same character as the reference sheet, medium shot, cartoon background."
        )
        draw(job, prompt, dest, size)
