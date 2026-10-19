from __future__ import annotations

import re
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from toon.assemble import ffmpeg_available
from toon.jobs import Job, list_jobs, remove_job
from toon.pipeline import run
from toon.settings import load_settings
from toon.spend import BudgetExceeded

ROOT = Path(__file__).resolve().parent
settings = load_settings()
app = FastAPI(title="toon")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

_lock = threading.Lock()
_running: set[str] = set()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ffmpeg": ffmpeg_available(),
        "story": bool(settings.openai_api_key),
        "images": settings.image_backend or "",
        "speech": settings.speech_backend or "",
        "animation": settings.animation_enabled,
        "max_usd": settings.max_usd_per_job,
    }


@app.get("/api/jobs")
def jobs() -> list[dict]:
    return list_jobs(settings)


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
            raise ValueError("invalid job id")
        return Job.open(settings, job_id).public_view()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "job not found") from exc


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
            raise ValueError("invalid job id")
        remove_job(settings, job_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "job not found") from exc
    return {"ok": True}


@app.post("/api/jobs")
async def create_job(
    description: str = Form(...),
    aspect: str = Form("9:16"),
    duration: int = Form(30),
    tier: str = Form("still"),
    code: str = Form(""),
    image: UploadFile | None = File(None),
) -> dict:
    text = description.strip()
    if not text:
        raise HTTPException(400, "Write a short description first.")
    if aspect not in {"9:16", "16:9"}:
        aspect = "9:16"
    if duration not in {15, 30, 45}:
        duration = 30
    if tier != "animated" or not settings.animation_enabled:
        tier = "still"
    demo = text.lower().startswith("demo:")
    required = settings.access_code
    if required and not demo and code.strip() != required:
        raise HTTPException(403, "An access code is required to generate videos on this demo.")
    job = Job.create(
        settings,
        {
            "description": text[:2000],
            "aspect": aspect,
            "duration": duration,
            "tier": tier,
            "demo": demo,
        },
    )
    if image is not None and image.filename:
        data = await image.read()
        try:
            name = job.save_upload(image.filename, data)
        except ValueError as exc:
            remove_job(settings, job.id)
            raise HTTPException(400, str(exc)) from exc
        brief = job.read_json("brief.json")
        brief["upload"] = name
        job.write_json("brief.json", brief)
    _start(job.id, demo=demo)
    return job.public_view()


@app.get("/api/jobs/{job_id}/file/{kind}/{filename}")
def job_file(job_id: str, kind: str, filename: str) -> FileResponse:
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
            raise ValueError("invalid job id")
        opened = Job.open(settings, job_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "job not found") from exc
    if kind not in {"frames", "cast", "upload", "out"}:
        raise HTTPException(404, "file not found")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", filename):
        raise HTTPException(404, "file not found")
    base = opened.root.resolve()
    folder = base if kind in {"upload", "out"} else (base / kind).resolve()
    path = (folder / filename).resolve()
    if path.parent != folder or not path.is_file():
        raise HTTPException(404, "file not found")
    if kind == "out" and filename not in {"final.mp4", "story.json", "captions.srt"}:
        raise HTTPException(404, "file not found")
    if kind == "upload" and not filename.startswith("upload."):
        raise HTTPException(404, "file not found")
    return FileResponse(path)


def _start(job_id: str, demo: bool = False) -> None:
    with _lock:
        if job_id in _running:
            return
        _running.add(job_id)

    def worker() -> None:
        job = Job.open(settings, job_id)
        try:
            run(job, demo=demo)
        except (BudgetExceeded, Exception) as exc:  # noqa: BLE001 — surface stage errors on the page
            job.write_status(job.read_json("status.json").get("stage", "story"), str(exc), error=str(exc))
        finally:
            with _lock:
                _running.discard(job_id)

    threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    webbrowser.open("http://127.0.0.1:8787")
    uvicorn.run("app:app", host="127.0.0.1", port=8787, reload=False)
