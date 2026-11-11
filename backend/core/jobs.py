"""
ASYNC_JOBS=true: long requests (scan / fix / proof / re-scan) answer at once with a job id,
and the dashboard polls GET /api/jobs/<id> until the result is ready.

Why: some hosts cut any request that takes longer than a few minutes (Azure App Service: 230 s),
and a PayPal Sandbox proof can take 1-3 minutes. The dashboard already understands job ids
(frontend-react/src/lib/checkout/api.ts, pollJob), so nothing changes for the user.

The job runs the SAME endpoint inside this server (an internal call with a secret header), so
the results are exactly what the normal request would return. Off by default.
"""

import asyncio
import os
import secrets
import time
import uuid

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

INTERNAL_HEADER = "x-checkoutpilot-internal"
_TOKEN = secrets.token_hex(16)        # new every start, never sent to a browser
KEEP_SECONDS = 3600                   # finished jobs are forgotten after an hour
STAGES = {
    "/api/scan": "Scanning the store",
    "/api/fix": "Writing the fix",
    "/api/verify": "Making PayPal Sandbox payments",
}

_jobs: dict[str, dict] = {}
_tasks: set = set()


def enabled() -> bool:
    return os.getenv("ASYNC_JOBS", "false").strip().lower() in ("1", "true", "yes")


def is_internal(request: Request) -> bool:
    """True for the job's own call to the endpoint (it must not be limited or queued again)."""
    return secrets.compare_digest(request.headers.get(INTERNAL_HEADER, ""), _TOKEN)


def _stage(path: str) -> str:
    if path.endswith("/rescan"):
        return "Scanning the fixed copy"
    return next((text for prefix, text in STAGES.items() if path.startswith(prefix)), "Working")


def _forget_old(now: float) -> None:
    for job_id in [j for j, job in _jobs.items() if job["status"] in ("succeeded", "failed")
                   and now - job["updated"] > KEEP_SECONDS]:
        _jobs.pop(job_id, None)


async def _run(app, job: dict, path: str, body: bytes, content_type: str) -> None:
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://checkoutpilot.internal",
                                     timeout=None) as client:
            response = await client.post(path, content=body, headers={
                "content-type": content_type, INTERNAL_HEADER: _TOKEN})
        try:
            data = response.json()
        except ValueError:
            data = {"detail": response.text[:300]}
        if response.status_code < 400:
            job.update(status="succeeded", progress=100, result=data)
        else:
            detail = data.get("detail", data) if isinstance(data, dict) else data
            job.update(status="failed", error=detail if isinstance(detail, str) else str(detail),
                       error_status=response.status_code)
    except Exception as exc:  # never leave a job "running" forever
        job.update(status="failed", error=f"The server could not finish this step: {exc}")
    job["updated"] = time.time()


async def start(request: Request) -> JSONResponse:
    """Accept the request, run it in the background, answer with the job id (HTTP 202)."""
    now = time.time()
    _forget_old(now)
    job_id = "job_" + uuid.uuid4().hex[:12]
    job = {"job_id": job_id, "status": "running", "stage": _stage(request.url.path), "progress": None,
           "created": now, "updated": now}
    _jobs[job_id] = job
    body = await request.body()
    task = asyncio.create_task(_run(request.app, job, request.url.path, body,
                                    request.headers.get("content-type", "application/json")))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return JSONResponse(status_code=202, content=public(job))


def public(job: dict) -> dict:
    """What the dashboard sees (no internal timestamps)."""
    return {k: v for k, v in job.items() if k not in ("created", "updated")}


def get(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    return public(job) if job else None
