"""
CheckoutPilot backend - main entry point.

Run from the project root folder:
    uvicorn backend.main:app --reload

Then open:
    http://localhost:8000/docs   (interactive API documentation)
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router
from backend.core import free_tier, hosting, jobs
from backend.core.config import settings

API_DESCRIPTION = """
CheckoutPilot finds what a store's PayPal checkout is missing, writes the upgrade,
and proves it works with a real PayPal **Sandbox** payment before the merchant approves.

* **Scan** (`POST /api/scan`): FIND and RANK issues from a store URL.
* **Verify** (`POST /api/verify`): PROVE a checkout works with real PayPal Sandbox payments.
* **Reports** (`GET /api/reports/{scan_id}`): read a saved scan.
* Screenshots are served under `/files/...`.

Sandbox only: the PayPal client refuses live API URLs. Full field reference: `docs/api_contract.md`.
"""

OPENAPI_TAGS = [
    {"name": "Health", "description": "Check that the API is running."},
    {"name": "Scan", "description": "FIND: audit a store's PayPal checkout and rank the issues."},
    {"name": "Verify", "description": "PROVE: real PayPal Sandbox test purchases before and after an upgrade."},
    {"name": "Reports", "description": "Saved scan results."},
]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Hosted mode (START_DEMO_STORES=true): run the example stores inside this service."""
    free_tier.apply()  # FREE_TIER=true: low-memory settings for a 512 MB free plan (off by default)
    hosting.start_demo_stores()
    yield
    hosting.stop_demo_stores()


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=settings.app_version,
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    servers=hosting.api_servers(),
    license_info={"name": "MIT", "url": "https://github.com/shravanisy2006/CheckoutPilot/blob/main/LICENSE"},
    contact={"name": "CheckoutPilot team", "url": "https://github.com/shravanisy2006/CheckoutPilot"},
)

# Hosted mode: per-visitor limits on scan/fix/verify and clean-up of old screenshots (off locally).
app.middleware("http")(hosting.make_middleware(Path("outputs")))

# CORS is added last so it wraps everything (also the hosting middleware's 202/429 answers).
# CORS_ORIGIN_REGEX lets a separately hosted dashboard call this API, e.g. https://.*\.vercel\.app
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=os.getenv("CORS_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/jobs/{job_id}", include_in_schema=False)
def job_status(job_id: str):
    """Progress of a long step (only used when ASYNC_JOBS=true, i.e. on a hosted server)."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found (the server may have restarted).")
    return job


app.include_router(api_router)

# Screenshots and other generated files (outputs/ is git-ignored) are served at
# /files/..., e.g. outputs/verifications/x/02_success_page.png ->
# /files/verifications/x/02_success_page.png. See docs/api_contract.md.
OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(exist_ok=True)
app.mount("/files", StaticFiles(directory=OUTPUTS_DIR), name="files")


DASHBOARD = hosting.dashboard_dir()

if DASHBOARD is None:

    @app.get("/")
    def root() -> dict:
        """Friendly message at the root URL."""
        return {"message": "CheckoutPilot API is running. Visit /docs for the API documentation."}

else:
    # Hosted mode: the dashboard is served from this same URL (no CORS, one link for judges).
    @app.get("/{path:path}", include_in_schema=False)
    def dashboard(path: str):
        return hosting.dashboard_response(DASHBOARD, path)
