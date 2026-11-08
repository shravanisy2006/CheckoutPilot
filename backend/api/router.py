"""
Combines all route files into one router.

To add a new group of endpoints:
  1. Create a new file in backend/api/routes/
  2. Import its router below and add one `include_router` line.
"""

from fastapi import APIRouter

from backend.api.routes import health, reports, scan, verify

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(scan.router)
api_router.include_router(reports.router)
api_router.include_router(verify.router)
