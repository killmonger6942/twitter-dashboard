import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from backend.config import DB_PATH, settings
from backend.middleware.auth import AuthMiddleware
from backend.models.database import Account, async_session, init_db
from backend.routes import accounts, analytics, auth, behavior, content, monitor, personas
from backend.scheduler import scheduler
from backend.services import behavior_engine, browser_service, follow_campaign, publisher


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.start()
    await _auto_recover()
    _schedule_publisher()
    yield
    scheduler.shutdown(wait=False)
    await browser_service.shutdown()


async def _auto_recover():
    try:
        await behavior_engine.auto_recover()
        await follow_campaign.auto_recover_campaigns()
    except Exception as e:
        print(f"[recovery] Auto-recovery error: {e}", flush=True)


def _schedule_publisher():
    if not (settings.github_token and settings.status_repo):
        print("[publisher] disabled (set GITHUB_TOKEN and STATUS_REPO to enable)", flush=True)
        return
    scheduler.add_job(
        publisher.publish_safe,
        "interval",
        minutes=settings.publish_interval_minutes,
        id="status_publisher",
        replace_existing=True,
        next_run_time=datetime.now(),  # publish once shortly after startup, then on interval
    )
    print(
        f"[publisher] every {settings.publish_interval_minutes}m -> "
        f"{settings.status_repo}/{settings.status_path}",
        flush=True,
    )


app = FastAPI(title="Twitter Dashboard", lifespan=lifespan)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(content.router)
app.include_router(personas.router)
app.include_router(monitor.router)
app.include_router(behavior.router)
app.include_router(analytics.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/status")
async def health_status():
    has_gemini = bool(settings.gemini_api_key and len(settings.gemini_api_key) > 5)

    chrome_path = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome_path:
        for p in [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]:
            if Path(p).exists():
                chrome_path = p
                break
    has_browser = chrome_path is not None

    account_count = 0
    logged_in_count = 0
    try:
        async with async_session() as session:
            result = await session.execute(select(func.count(Account.id)))
            account_count = result.scalar() or 0
            result2 = await session.execute(
                select(func.count(Account.id)).where(Account.is_logged_in == True)
            )
            logged_in_count = result2.scalar() or 0
    except Exception:
        pass

    return {
        "status": "ok",
        "api_keys": {"gemini": has_gemini},
        "browser": has_browser,
        "accounts": account_count,
        "logged_in_accounts": logged_in_count,
        "database": DB_PATH.exists(),
    }
