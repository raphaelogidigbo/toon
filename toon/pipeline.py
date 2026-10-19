from __future__ import annotations

from toon.assemble import assemble
from toon.cast import build_cast
from toon.frames import build_frames
from toon.jobs import Job
from toon.motion import build_motion
from toon.speech import build_speech
from toon.story import write_story
from toon.vision import describe_upload


def _demo(job: Job) -> None:
    brief = job.read_json("brief.json")
    if not job.exists("story.json"):
        job.write_json(
            "story.json",
            {
                "title": "Demo",
                "aspect": brief.get("aspect", "9:16"),
                "size": {"width": 720, "height": 1280},
                "characters": [{"id": "hero", "name": "Hero", "look": "small robot", "voice": "alloy"}],
                "shots": [
                    {
                        "visual": brief.get("description", "A cartoon scene"),
                        "speaker": "hero",
                        "line": "This is a demo story.",
                        "caption": "Demo",
                        "seconds": 4,
                        "motion": "hold",
                    }
                ],
            },
        )
    for stage in ("story", "cast", "frames", "speech", "motion", "assemble"):
        job.mark_stage(stage, "done")


def run(job: Job, demo: bool = False) -> None:
    job.write_status("story", "Writing the story")
    if demo:
        _demo(job)
        job.write_status("assemble", "Demo ready. Add API keys for a real video.", done=True)
        return
    note = describe_upload(job)
    write_story(job, note)
    job.mark_stage("story", "done")

    job.write_status("cast", "Drawing characters")
    build_cast(job)
    job.mark_stage("cast", "done")

    job.write_status("frames", "Drawing shots")
    build_frames(job)
    job.mark_stage("frames", "done")

    job.write_status("speech", "Recording voices")
    build_speech(job)
    job.mark_stage("speech", "done")

    job.write_status("motion", "Building shots")
    build_motion(job)
    job.mark_stage("motion", "done")

    job.write_status("assemble", "Cutting the video")
    assemble(job)
    job.mark_stage("assemble", "done")
    job.write_status("assemble", "Ready", done=True)
