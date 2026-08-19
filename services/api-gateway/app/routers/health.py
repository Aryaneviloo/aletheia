"""
api_gateway.app.routers.health
=================================

Liveness and readiness endpoints

/health/live: checks if the process is live and returns 200
              docker uses this to restart the container

/health/ready: is this process ready to serve the traffic?
               returns 200 if all critical dependencies are
               are reachable
               
A process can be live not yet ready 
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from aletheia_core.config import get_settings
from aletheia_core.db.base import SessionLocal
from aletheia_core.logging import get_logger

router = APIRouter(prefix="/health", tags=["health"])
log = get_logger(__name__)


@router.get("/live")
async def liveness():
    return {"status": "ok"}

@router.get("/ready")
async def readiness():
    """Check all the critical dependencies"""

    settings = get_settings()
    checks: dict[str, bool] = {}

    #Postgres
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["postgres"] = True
    except Exception as e:
        log.warnign("readiness_postgres_failed", error=str(e))
        checks["postgres"] = False

    #inference-service
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.inference_service_ur}/health")
            checks['inference_service'] = resp.status_code == 200

    except Exception as e:
        log.warning("readiness_inference_failed", error=str(e))
        checks["inference_service"] = False
    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content = {"status": "ok" if all_ok else "degraded", "checks": checks},
    )



