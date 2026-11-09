"""
CheckoutPilot backend - main entry point.

Run from the project root folder:
    uvicorn backend.main:app --reload

Then open:
    http://localhost:8000/docs   (interactive API documentation)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router
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

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    servers=[{"url": "http://localhost:8000", "description": "Local CheckoutPilot backend"}],
    license_info={"name": "MIT", "url": "https://github.com/shravanisy2006/CheckoutPilot/blob/main/LICENSE"},
    contact={"name": "CheckoutPilot team", "url": "https://github.com/shravanisy2006/CheckoutPilot"},
)

# CORS lets the Streamlit frontend (a different port) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Screenshots and other generated files (outputs/ is git-ignored) are served at
# /files/..., e.g. outputs/verifications/x/02_success_page.png ->
# /files/verifications/x/02_success_page.png. See docs/api_contract.md.
OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(exist_ok=True)
app.mount("/files", StaticFiles(directory=OUTPUTS_DIR), name="files")


@app.get("/")
def root() -> dict:
    """Friendly message at the root URL."""
    return {"message": "CheckoutPilot API is running. Visit /docs for the API documentation."}
