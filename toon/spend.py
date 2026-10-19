from __future__ import annotations

from toon.jobs import Job

# Rough published rates used only as a stop-before-call guard, not an invoice.
RATES = {
    "story": 0.01,
    "image": 0.04,
    "tts": 0.02,
    "i2v_second": 0.09,
    "lipsync_second": 0.02,
}


class BudgetExceeded(RuntimeError):
    pass


def spent(job: Job) -> float:
    if not job.exists("spend.json"):
        return 0.0
    return float(job.read_json("spend.json").get("usd") or 0)


def charge(job: Job, kind: str, units: float = 1.0, note: str = "") -> None:
    cost = round(RATES[kind] * units, 4)
    cap = job.settings.max_usd_per_job
    current = spent(job)
    if current + cost > cap:
        raise BudgetExceeded(f"This step would pass the ${cap:.2f} limit (already ${current:.2f}).")
    data = job.read_json("spend.json") if job.exists("spend.json") else {"usd": 0.0, "calls": []}
    data["usd"] = round(float(data.get("usd") or 0) + cost, 4)
    data.setdefault("calls", []).append({"kind": kind, "usd": cost, "note": note})
    job.write_json("spend.json", data)
