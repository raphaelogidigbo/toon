from __future__ import annotations

import subprocess
from pathlib import Path

from toon.jobs import Job
from toon.motion import MotionError, _run, ffmpeg_bin


def assemble(job: Job) -> None:
    if job.exists("final.mp4"):
        return
    story = job.read_json("story.json")
    clips = []
    for index, shot in enumerate(story["shots"], start=1):
        video = job.root / "clips" / f"{index:02d}.mp4"
        audio = job.root / "audio" / f"{index:02d}.mp3"
        merged = job.root / "clips" / f"{index:02d}_mix.mp4"
        if not video.exists():
            raise MotionError(f"missing clip for shot {index}")
        _mix(video, audio if audio.exists() else None, merged, int(shot.get("seconds") or 4))
        clips.append(merged)
    list_file = job.root / "clips.txt"
    list_file.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
    silent = job.root / "joined.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(silent)])
    final = job.root / "final.mp4"
    music = _music(job.settings.root)
    _finish(silent, job.root / "captions.srt", music, final)
    job.write_json(
        "meta.json",
        {
            "ai_generated": True,
            "title": story.get("title", ""),
            "tier": job.read_json("brief.json").get("tier", "still"),
            "aspect": story.get("aspect"),
            "spend_usd": job.read_json("spend.json").get("usd", 0) if job.exists("spend.json") else 0,
        },
    )


def _mix(video: Path, audio: Path | None, dest: Path, seconds: int) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    if audio is None:
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                str(dest),
            ]
        )
        return
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ]
    )


def _finish(video: Path, srt: Path, music: Path | None, dest: Path) -> None:
    # Run from the job folder and reference captions.srt by name only.
    # Absolute Windows paths ("C:\...") break ffmpeg's filter parser even when escaped.
    caption = srt.name.replace("'", r"\'")
    video_filter = f"subtitles={caption}"
    cwd = srt.parent
    if music is None:
        _run(
            ["ffmpeg", "-y", "-i", video.name, "-vf", video_filter, "-c:a", "copy", dest.name],
            cwd=cwd,
        )
        return
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video.name,
            "-i",
            str(music),
            "-filter_complex",
            f"[0:v]{video_filter}[v];[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            dest.name,
        ],
        cwd=cwd,
    )


def _music(root: Path) -> Path | None:
    folder = root / "assets" / "music"
    if not folder.exists():
        return None
    for pattern in ("*.mp3", "*.wav", "*.m4a"):
        found = next(folder.glob(pattern), None)
        if found:
            return found
    return None


def ffmpeg_available() -> bool:
    try:
        subprocess.run([ffmpeg_bin(), "-version"], capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
