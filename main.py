from __future__ import annotations

import asyncio
import datetime
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from crosswords import DATE_FORMAT, build_crosswords_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
log = logging.getLogger("crosswords.api")

ROOT = Path(__file__).parent
MAX_COUNT_LIMIT = 15
JOB_TTL_SECONDS = 600  # finished jobs are kept this long for the UI to fetch the PDF

app = FastAPI(title="Crosswords", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")


def _load_defaults() -> dict:
    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f) or {}
    return {
        "from_date": cfg.get("last-date", "2026/01/01"),
        "max_count": min(int(cfg.get("max-count", MAX_COUNT_LIMIT)), MAX_COUNT_LIMIT),
        "target_page": int(cfg.get("target-page", 6)),
    }


@dataclass
class Job:
    id: str
    from_date: str
    max_count: int
    target_page: int
    progress: dict = field(default_factory=lambda: {"phase": "queued", "done": 0, "total": 0, "current": ""})
    pdf: Optional[bytes] = None
    processed: list[str] = field(default_factory=list)
    error: Optional[str] = None
    finished: bool = False
    finished_at: float = 0.0


JOBS: dict[str, Job] = {}


def _gc_jobs():
    now = time.time()
    stale = [jid for jid, j in JOBS.items() if j.finished and (now - j.finished_at) > JOB_TTL_SECONDS]
    for jid in stale:
        JOBS.pop(jid, None)


def _run_job(job: Job):
    def cb(ev: dict):
        job.progress = ev

    try:
        pdf, processed = build_crosswords_pdf(
            from_date=job.from_date,
            max_count=job.max_count,
            target_page=job.target_page,
            progress_cb=cb,
        )
        job.pdf = pdf
        job.processed = processed
        if not pdf:
            job.error = "No crosswords found in that range"
    except Exception as e:
        log.exception("Job %s failed", job.id)
        job.error = str(e)
    finally:
        job.finished = True
        job.finished_at = time.time()


class RunRequest(BaseModel):
    from_date: str = Field(pattern=r"^\d{4}/\d{2}/\d{2}$")
    max_count: int = Field(ge=1, le=MAX_COUNT_LIMIT)
    target_page: int = Field(ge=0, le=50)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/defaults")
def defaults():
    return {**_load_defaults(), "max_count_limit": MAX_COUNT_LIMIT}


@app.post("/api/run")
async def run(req: RunRequest):
    try:
        datetime.datetime.strptime(req.from_date, DATE_FORMAT)
    except ValueError:
        raise HTTPException(400, "from_date must be YYYY/MM/DD")
    _gc_jobs()
    job = Job(id=uuid.uuid4().hex, from_date=req.from_date, max_count=req.max_count, target_page=req.target_page)
    JOBS[job.id] = job
    asyncio.get_event_loop().run_in_executor(None, _run_job, job)
    return {"job_id": job.id}


def _next_date(last: str) -> str:
    return (datetime.datetime.strptime(last, DATE_FORMAT) + datetime.timedelta(days=1)).strftime(DATE_FORMAT)


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")

    async def stream():
        last_payload = None
        while not job.finished:
            payload = json.dumps(job.progress)
            if payload != last_payload:
                yield f"event: progress\ndata: {payload}\n\n"
                last_payload = payload
            await asyncio.sleep(0.25)
        if job.error:
            yield f"event: error\ndata: {json.dumps({'message': job.error})}\n\n"
        else:
            done_payload = {
                "count": len(job.processed),
                "first": job.processed[0] if job.processed else None,
                "last": job.processed[-1] if job.processed else None,
                "next": _next_date(job.processed[-1]) if job.processed else None,
                "pdf_url": f"/api/jobs/{job.id}/pdf",
            }
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}/pdf")
def job_pdf(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if not job.finished:
        raise HTTPException(409, "job not finished")
    if job.error or not job.pdf:
        raise HTTPException(404, job.error or "no pdf")
    fname = f"crosswords-{job.processed[0].replace('/', '-')}_to_{job.processed[-1].replace('/', '-')}.pdf"
    return Response(
        content=job.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Processed-Count": str(len(job.processed)),
            "X-First-Date": job.processed[0],
            "X-Last-Date": job.processed[-1],
            "X-Next-Date": _next_date(job.processed[-1]),
        },
    )


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
