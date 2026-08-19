"""
Meeting Note Taker API - Main FastAPI application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv

from .routers import meetings, auth, integration, realtime

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Meeting Note Taker API",
    description="AI-powered meeting transcription and summarization service",
    version="1.0.0"
)

# CORS middleware
# Read allowed origins from CORS_ORIGINS env var (comma-separated)
cors_origins_env = os.getenv("CORS_ORIGINS", "")
if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    cors_origins = ["http://localhost:9002", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)  # Auth routes (login, verify, logout)
app.include_router(meetings.router)  # Meeting routes (protected - JWT or API key)
app.include_router(integration.router)  # Integration routes (API key only)
app.include_router(realtime.router)  # Real-time transcription WebSocket

from api.config.edition import IS_CLOUD
# Cloud-only routes (analytics, teams, billing) — registered only in cloud mode
if IS_CLOUD:
    try:
        from api.routers.cloud import analytics, teams, billing, manor_oauth
        app.include_router(analytics.router)
        app.include_router(teams.router)
        app.include_router(billing.router)
        app.include_router(manor_oauth.router)
    except ImportError:
        pass  # Cloud modules not available


@app.get("/")
async def root():
    """Root endpoint"""
    return JSONResponse({
        "message": "Meeting Note Taker API",
        "version": "1.0.0",
        "status": "running"
    })


@app.get("/health")
@app.get("/api/health")  # nginx only proxies /api to the backend, so bare
                         # /health is shadowed by the SPA in production.
async def health_check():
    """Health check endpoint with dependency checks"""
    checks = {}

    # Check PostgreSQL
    try:
        from database.db import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Check Redis
    try:
        import redis
        r = redis.from_url(os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"))
        r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    # Check MinIO / storage
    try:
        from api.services.storage_service import storage
        s = storage()
        # Just instantiating the storage client is enough to verify connectivity
        checks["storage"] = "ok"
    except Exception:
        checks["storage"] = "unavailable"

    # Check that a Celery worker is actually consuming.  A reachable broker
    # with no worker behind it is what leaves meetings stuck in PROCESSING,
    # and nothing else here would surface it.
    try:
        from celery_tasks import celery_app
        replies = celery_app.control.ping(timeout=1.0) or []
        checks["celery_workers"] = "ok" if replies else "no workers responding"
    except Exception:
        checks["celery_workers"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse({
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "version": "1.0.0",
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
