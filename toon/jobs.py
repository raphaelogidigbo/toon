from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toon.settings import Settings

STAGES = ("story", "cast", "frames", "speech", "motion", "assemble")


def new_job_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_id(job_id: str) -> str:
    cleaned = (job_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cleaned):
        raise ValueError("invalid job id")
    if cleaned in {".", ".."} or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError("invalid job id")
    return cleaned


def job_dir(settings: Settings, job_id: str) -> Path:
    name = safe_id(job_id)
    base = settings.output_dir.resolve()
    root = (base / name).resolve()
    if root.parent != base:
        raise ValueError("invalid job id")
    return root


class Job:
    def __init__(self, settings: Settings, job_id: str):
        self.settings = settings
        self.id = safe_id(job_id)
        self.root = job_dir(settings, self.id)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "cast").mkdir(exist_ok=True)
        (self.root / "frames").mkdir(exist_ok=True)
        (self.root / "audio").mkdir(exist_ok=True)
        (self.root / "clips").mkdir(exist_ok=True)

    @classmethod
    def create(cls, settings: Settings, brief: dict[str, Any]) -> Job:
        job = cls(settings, new_job_id())
        job.write_json("brief.json", brief)
        job.write_status(stage="queued", message="Waiting to start", done=False)
        job.write_json("spend.json", {"usd": 0.0, "calls": []})
        job.write_json(
            "meta.json",
            {
                "ai_generated": True,
                "tier": brief.get("tier", "still"),
                "aspect": brief.get("aspect", "9:16"),
            },
        )
        return job

    @classmethod
    def open(cls, settings: Settings, job_id: str) -> Job:
        job = cls(settings, job_id)
        if not (job.root / "brief.json").exists():
            raise FileNotFoundError(job_id)
        return job

    def path(self, name: str) -> Path:
        return self.root / name

    def exists(self, name: str) -> bool:
        return self.path(name).is_file() and self.path(name).stat().st_size > 0

    def read_json(self, name: str) -> Any:
        return json.loads(self.path(name).read_text(encoding="utf-8"))

    def write_json(self, name: str, data: Any) -> None:
        target = self.path(name)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(target)

    def write_status(self, stage: str, message: str, done: bool = False, error: str = "") -> None:
        previous = {}
        if self.exists("status.json"):
            previous = self.read_json("status.json")
        stages = previous.get("stages") or {name: "pending" for name in STAGES}
        if stage in stages and not error:
            stages[stage] = "done" if done else "running"
        self.write_json(
            "status.json",
            {
                "id": self.id,
                "stage": stage,
                "message": message,
                "error": error,
                "done": done and stage == "assemble",
                "failed": bool(error),
                "stages": stages,
                "updated": datetime.now(timezone.utc).isoformat(),
            },
        )

    def mark_stage(self, stage: str, state: str) -> None:
        status = self.read_json("status.json") if self.exists("status.json") else {"stages": {}}
        status.setdefault("stages", {name: "pending" for name in STAGES})
        status["stages"][stage] = state
        status["stage"] = stage
        status["updated"] = datetime.now(timezone.utc).isoformat()
        self.write_json("status.json", status)

    def save_upload(self, filename: str, data: bytes) -> str:
        ext = Path(filename).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("image must be png, jpg, or webp")
        if len(data) > 8_000_000:
            raise ValueError("image is larger than 8MB")
        dest = self.root / f"upload{ext}"
        dest.write_bytes(data)
        return dest.name

    def public_view(self) -> dict[str, Any]:
        status = self.read_json("status.json") if self.exists("status.json") else {}
        brief = self.read_json("brief.json") if self.exists("brief.json") else {}
        story = self.read_json("story.json") if self.exists("story.json") else None
        spend = self.read_json("spend.json") if self.exists("spend.json") else {"usd": 0}
        frames = sorted(p.name for p in (self.root / "frames").glob("*") if p.is_file())
        upload = next((p.name for p in self.root.glob("upload.*") if p.is_file()), "")
        return {
            "id": self.id,
            "brief": brief,
            "status": status,
            "story": story,
            "spend": spend,
            "frames": frames,
            "upload": upload,
            "video": "final.mp4" if self.exists("final.mp4") else "",
        }


def list_jobs(settings: Settings) -> list[dict[str, Any]]:
    if not settings.output_dir.exists():
        return []
    jobs = []
    for folder in sorted(settings.output_dir.iterdir(), reverse=True):
        if not folder.is_dir() or not (folder / "brief.json").is_file():
            continue
        try:
            jobs.append(Job.open(settings, folder.name).public_view())
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return jobs


def remove_job(settings: Settings, job_id: str) -> None:
    root = job_dir(settings, job_id)
    if not (root / "brief.json").is_file():
        raise FileNotFoundError(job_id)
    shutil.rmtree(root)
