"""FastAPI routes — REST layer per PROJECT_SPEC §A.

Endpoints:
  POST   /runs                    — start a pipeline run (background task)
  GET    /runs                    — list known jobs (in-memory registry)
  GET    /runs/{job_id}           — job status + latest checkpoint progress
  GET    /runs/{job_id}/export    — stream the run's JSONL output
  GET    /coverage/{domain}       — taxonomy coverage analytics (DuckDB)
  GET    /healthz                 — liveness probe

The orchestrator owns long-running work; this module is a thin shell.
Jobs are tracked in a process-local registry (`JobRegistry`); restarting
the API drops in-flight handles — checkpoints remain on disk and can be
inspected via /runs/{job_id} after pointing at the last known run_id.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import config
from pipeline import checkpoint as ck
from pipeline import orchestrator
from pipeline.diversity import compute_vendi_score, coverage_gaps
from storage.store import Store


_log = logging.getLogger("sdf.api")

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class StartRunRequest(BaseModel):
    domain: str
    target: int = Field(gt=0)
    seed: Optional[int] = None
    resume: bool = True
    gen_batch_size: Optional[int] = Field(default=None, gt=0)


JobStatus = Literal["running", "done", "failed"]


class JobInfo(BaseModel):
    job_id: str
    domain: str
    target: int
    status: JobStatus
    run_id: Optional[str] = None
    output_path: Optional[str] = None
    accepted: int = 0
    rejected: int = 0
    last_node_idx: int = -1
    error: Optional[str] = None


class CoverageResponse(BaseModel):
    domain: str
    dimension: str
    counts: dict[str, int]
    gaps: dict[str, int] = Field(default_factory=dict)


class DiversityResponse(BaseModel):
    domain: str
    n_examples: int
    vendi_score: float


# ---------------------------------------------------------------------------
# Job registry — process-local, deliberately simple
# ---------------------------------------------------------------------------
class JobRegistry:
    """In-memory job tracker. One per FastAPI app (`app.state.jobs`)."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobInfo] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def add(self, info: JobInfo, task: asyncio.Task) -> None:
        async with self._lock:
            self._jobs[info.job_id] = info
            self._tasks[info.job_id] = task

    async def get(self, job_id: str) -> Optional[JobInfo]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def list(self) -> list[JobInfo]:
        async with self._lock:
            return list(self._jobs.values())

    async def update(self, job_id: str, **fields) -> None:
        async with self._lock:
            cur = self._jobs.get(job_id)
            if cur is None:
                return
            self._jobs[job_id] = cur.model_copy(update=fields)


def _registry(request: Request) -> JobRegistry:
    reg = getattr(request.app.state, "jobs", None)
    if reg is None:
        reg = JobRegistry()
        request.app.state.jobs = reg
    return reg


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------
async def _run_job(job_id: str, req: StartRunRequest, registry: JobRegistry) -> None:
    """Execute orchestrator.run and update the job record with the summary."""
    try:
        summary = await orchestrator.run(
            domain=req.domain,
            target=req.target,
            seed=req.seed,
            resume=req.resume,
            gen_batch_size=req.gen_batch_size,
        )
    except Exception as exc:  # noqa: BLE001 — funnel any failure into the job record
        _log.exception("job %s failed", job_id)
        await registry.update(job_id, status="failed", error=str(exc))
        return

    await registry.update(
        job_id,
        status="done",
        run_id=summary.get("run_id"),
        output_path=summary.get("output_path"),
        accepted=int(summary.get("accepted", 0)),
        rejected=int(summary.get("rejected", 0)),
        last_node_idx=int(summary.get("last_node_idx", -1)),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.post("/runs", response_model=JobInfo, status_code=202)
async def start_run(req: StartRunRequest, request: Request) -> JobInfo:
    """Kick off a pipeline run as a background task. Returns immediately."""
    registry = _registry(request)
    job_id = uuid.uuid4().hex
    info = JobInfo(
        job_id=job_id, domain=req.domain, target=req.target, status="running",
    )
    task = asyncio.create_task(_run_job(job_id, req, registry), name=f"sdf.job.{job_id}")
    await registry.add(info, task)
    _log.info("started job=%s domain=%s target=%d", job_id, req.domain, req.target)
    return info


@router.get("/runs", response_model=list[JobInfo])
async def list_runs(request: Request) -> list[JobInfo]:
    return await _registry(request).list()


@router.get("/runs/{job_id}", response_model=JobInfo)
async def get_run(job_id: str, request: Request) -> JobInfo:
    info = await _registry(request).get(job_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")

    # While a job is in-flight, augment with the latest checkpoint counters.
    if info.status == "running":
        latest = await ck.load_latest(domain=info.domain)
        if latest:
            info = info.model_copy(update={
                "run_id": latest.get("run_id"),
                "accepted": int(latest.get("accepted_count", 0)),
                "rejected": int(latest.get("rejected_count", 0)),
                "last_node_idx": int(latest.get("last_node_idx", -1)),
            })
    return info


@router.get("/runs/{job_id}/export")
async def export_run(job_id: str, request: Request) -> FileResponse:
    info = await _registry(request).get(job_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")
    if not info.output_path:
        raise HTTPException(status_code=409, detail="output not ready yet")
    path = Path(info.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"output file missing: {path}")
    return FileResponse(
        path=path, media_type="application/x-ndjson", filename=path.name,
    )


@router.get("/coverage/{domain}", response_model=CoverageResponse)
async def coverage(
    domain: str,
    dimension: str,
    expected_per_value: Optional[int] = None,
) -> CoverageResponse:
    """Counts of accepted examples per taxonomy value for one dimension.

    If `expected_per_value` is provided, the response also includes a
    `gaps` map of {value: deficit} for under-represented values.
    """
    async with Store() as store:
        counts = await store.coverage(domain=domain, dimension=dimension)
    gaps = coverage_gaps(counts, expected_per_value) if expected_per_value else {}
    return CoverageResponse(
        domain=domain, dimension=dimension, counts=counts, gaps=gaps,
    )


@router.get("/diversity/{domain}", response_model=DiversityResponse)
async def diversity(domain: str) -> DiversityResponse:
    """Vendi-score diversity of all accepted embeddings in the domain."""
    async with Store() as store:
        embeddings = await store.all_embeddings(domain=domain)
    return DiversityResponse(
        domain=domain,
        n_examples=len(embeddings),
        vendi_score=compute_vendi_score(embeddings),
    )
