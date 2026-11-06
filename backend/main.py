"""
CheckoutPilot backend - main entry point.

Run from the project root folder:
    uvicorn backend.main:app --reload

Then open:
    http://localhost:8000/docs   (interactive API documentation)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.router import api_router
from backend.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Audits a store's PayPal checkout, ranks fixes and verifies them in the PayPal Sandbox.",
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


@app.get("/")
def root() -> dict:
    """Friendly message at the root URL."""
    return {"message": "CheckoutPilot API is running. Visit /docs for the API documentation."}
