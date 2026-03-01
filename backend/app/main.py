import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .github_webhook import router as github_router
from .auth import router as auth_router
from .review_engine import review_history
from .user_store import user_store

# ── Logging setup ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── FastAPI application ─────────────────────────────────────────────────────

app = FastAPI(
    title="AI Pull Request Guardian",
    description="Automated AI-powered code review for GitHub pull requests",
    version="2.0.0",
)

# CORS — allow dashboard to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (dashboard) ───────────────────────────────────────────────

STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── Routers ─────────────────────────────────────────────────────────────────

app.include_router(github_router, prefix="/webhooks/github", tags=["github"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])


# ── Dashboard (serves the UI) ──────────────────────────────────────────────

@app.get("/", tags=["dashboard"], include_in_schema=False)
def dashboard(request: Request):
    """Serve the landing page or dashboard based on login state."""
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)

    if user:
        return FileResponse(str(STATIC_DIR / "dashboard.html"))
    else:
        return FileResponse(str(STATIC_DIR / "index.html"))


# ── Health check ────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "ai-pr-guardian",
        "users": user_store.get_all_users_count(),
    }


# ── Stats and review history ───────────────────────────────────────────────

@app.get("/stats", tags=["dashboard"])
def get_stats(request: Request):
    """Return aggregate review statistics."""
    # Check if user is logged in — show their stats
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)

    if user:
        reviews = user.get('reviews', [])
    else:
        reviews = review_history  # fallback to global

    if not reviews:
        return {
            "total_reviews": 0,
            "avg_score": 0,
            "total_tokens": 0,
            "total_issues": 0,
        }

    return {
        "total_reviews": len(reviews),
        "avg_score": sum(r.get('score', 0) for r in reviews) / len(reviews),
        "total_tokens": sum(r.get('tokens', 0) for r in reviews),
        "total_issues": sum(r.get('total_issues', 0) for r in reviews),
    }


@app.get("/reviews", tags=["dashboard"])
def get_reviews(request: Request):
    """Return the review history (most recent first)."""
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)

    if user:
        reviews = user.get('reviews', [])
    else:
        reviews = review_history

    return list(reversed(reviews))


# ── Startup log ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("🛡️  AI PR Guardian v2.0 is running")
    logger.info("📊 Dashboard:  http://localhost:8000")
    logger.info("📚 API Docs:   http://localhost:8000/docs")
    logger.info("🔗 Webhook:    POST /webhooks/github")
    logger.info("🔐 OAuth:      GET /auth/login")
