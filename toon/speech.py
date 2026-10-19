from __future__ import annotations

from toon.jobs import Job
from toon.providers import speak


def build_speech(job: Job) -> None:
    story = job.read_json("story.json")
    voices = {item["id"]: item.get("voice", "alloy") for item in story["characters"]}
    captions = []
    cursor = 0.0
    for index, shot in enumerate(story["shots"], start=1):
        line = shot.get("line", "")
        dest = job.root / "audio" / f"{index:02d}.mp3"
        if line:
            speak(job, line, voices.get(shot["speaker"], "alloy"), dest)
        seconds = float(shot.get("seconds") or 4)
        if shot.get("caption"):
            captions.append((cursor, cursor + seconds, shot["caption"]))
        cursor += seconds
    _write_srt(job, captions)


def _write_srt(job: Job, captions: list[tuple[float, float, str]]) -> None:
    if job.exists("captions.srt"):
        return
    blocks = []
    for index, (start, end, text) in enumerate(captions, start=1):
        blocks.append(f"{index}\n{_stamp(start)} --> {_stamp(end)}\n{text}\n")
    (job.root / "captions.srt").write_text("\n".join(blocks), encoding="utf-8")


def _stamp(seconds: float) -> str:
    total = int(seconds * 1000)
    hours, rem = divmod(total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
