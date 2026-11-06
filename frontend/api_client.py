"""
Small helper for the frontend to talk to the backend API.

The frontend never imports backend code directly - it only makes HTTP calls.
That keeps the two apps independent: each can run on its own.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def check_backend_health() -> bool:
    """Return True if the backend is running and healthy."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=3)
        return response.status_code == 200
    except requests.RequestException:
        return False


def start_scan(store_url: str, include_mobile: bool = True) -> dict:
    """
    Ask the backend to scan a store.

    Returns the backend's JSON response, or an error dictionary if the
    backend cannot be reached.
    """
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/scan",
            json={"store_url": store_url, "include_mobile": include_mobile},
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        return {"status": "error", "message": f"Could not reach the backend: {error}", "gaps": []}
