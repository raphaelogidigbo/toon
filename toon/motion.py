from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from toon.jobs import Job
from toon.providers import animate, lipsync


class MotionError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def build_motion(job: Job) -> None:
    story = job.read_json("story.json")
    notes = []
    for index, shot in enumerate(story["shots"], start=1):
        frame = job.root / "frames" / f"{index:02d}.png"
        clip = job.root / "clips" / f"{index:02d}.mp4"
        audio = job.root / "audio" / f"{index:02d}.mp3"
        seconds = int(shot.get("seconds") or 4)
        made = False
        if shot.get("motion") == "i2v" and job.read_json("brief.json").get("tier") == "animated":
            made = animate(job, frame, shot["visual"], seconds, clip)
            if not made:
                notes.append(f"Shot {index} stayed a still (no video key or budget).")
        if not made:
            ken_burns(frame, clip, seconds, story["size"]["width"], story["size"]["height"])
        if audio.exists() and shot.get("motion") == "i2v":
            synced = job.root / "clips" / f"{index:02d}_talk.mp4"
            if lipsync(job, clip, audio, synced, seconds):
                shutil.move(synced, clip)
            else:
                notes.append(f"Shot {index} has captions instead of lip-sync.")
    if notes:
        (job.root / "motion_notes.txt").write_text("\n".join(notes), encoding="utf-8")


def ken_burns(image: Path, dest: Path, seconds: int, width: int, height: int) -> None:
    # zoompan filter expects width and height as separate integers.
    if dest.exists() and dest.stat().st_size > 0:
        return
    frames = max(seconds, 2) * 25
    zoom = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"zoompan=z='min(zoom+0.0012,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps=25,format=yuv420p"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image),
            "-vf",
            zoom,
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
    )


def _run(command: list[str], cwd: Path | None = None) -> None:
    if command and command[0] == "ffmpeg":
        command[0] = ffmpeg_bin()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, cwd=cwd)
    except FileNotFoundError as exc:
        raise MotionError(
            "ffmpeg is not installed or not on PATH. "
            "Install it with: winget install Gyan.FFmpeg"
        ) from exc
    if result.returncode != 0:
        tail = (result.stderr or "")[-500:]
        raise MotionError(f"ffmpeg failed: {tail}")
