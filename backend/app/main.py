"""FastAPI entrypoint — wires the database, REST routers, WebSocket feed, and the
scheduler into one app. Run from the repo root:

    uvicorn backend.app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import actions, auth, discovery, feed_ws, graph, leads, onboarding, views, webhooks
from .api.onboarding import ensure_default_fit
from .config import settings
from .database import init_db
from .scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_default_fit()  # seed a default Fit Model so the demo works immediately
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Rael", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(discovery.router)
app.include_router(leads.router)
app.include_router(views.router)
app.include_router(actions.router)
app.include_router(graph.router)
app.include_router(webhooks.router)
# WebSocket
app.include_router(feed_ws.router)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    return {
        "name": "Rael",
        "status": "online",
        "approval_mode": settings.approval_mode,
        "qualify_threshold": settings.qualify_threshold,
        "docs": "/docs",
        "scout": "POST /api/discovery/run",
    }


# ── Production static serving ────────────────────────────────────────────
# When frontend/dist exists (built via `npm run build`), FastAPI serves the SPA
# itself: one Railway service, same-origin /api and /ws — no CORS, no proxy.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = _DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
else:

    @app.get("/")
    async def root():
        return {"name": "Rael", "status": "online (API only — frontend/dist not built)", "docs": "/docs"}
