"""Publishes a sanitized, read-only analytics snapshot to a public GitHub repo file.

The control backend runs privately on this machine (it drives a real Chrome via
Playwright). It can't be reached from the public internet, so instead of exposing
it, we PUSH a JSON snapshot outward every `publish_interval_minutes` to a public
GitHub repo. A static, no-backend page on Vercel reads that file's raw URL.

Nothing sensitive (tokens, password hash, draft bodies, screenshots, target URLs)
is ever included -- only analytics the operator has chosen to make public.
"""

import base64
import json
from datetime import datetime, timedelta

import httpx
from sqlalchemy import case, func, select

from backend.config import settings
from backend.models.database import (
    Account,
    AnalyticsSnapshot,
    FollowCandidate,
    async_session,
)
from backend.routes.analytics import _unified_actions_query

GITHUB_API = "https://api.github.com"
_CAMPAIGN_STATES = ["discovered", "queued", "followed", "following", "skipped", "failed"]


async def _account_block(session, account: Account) -> dict:
    # --- profile stats + growth (mirrors analytics.profile_metrics) ---
    res = await session.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.account_id == account.id)
        .order_by(AnalyticsSnapshot.snapshot_date.desc())
        .limit(30)
    )
    snaps = list(res.scalars().all())
    snaps.reverse()
    latest = snaps[-1] if snaps else None
    first = snaps[0] if snaps else None

    growth: dict = {}
    if latest and first and len(snaps) > 1:
        growth = {
            "followers": latest.followers_count - first.followers_count,
            "following": latest.following_count - first.following_count,
            "tweets": latest.tweet_count - first.tweet_count,
        }

    # --- action summary, last 7 days (mirrors analytics.summary) ---
    since_7d = datetime.utcnow() - timedelta(days=7)
    unified = _unified_actions_query(account.id, since_7d)
    res = await session.execute(
        select(
            unified.c.action_type,
            func.count().label("total"),
            func.sum(case((unified.c.status == "done", 1), else_=0)).label("done"),
            func.sum(case((unified.c.status == "failed", 1), else_=0)).label("failed"),
        ).group_by(unified.c.action_type)
    )
    actions_7d = {
        row.action_type: {
            "total": int(row.total or 0),
            "done": int(row.done or 0),
            "failed": int(row.failed or 0),
        }
        for row in res.all()
    }

    # --- recent activity (mirrors analytics.recent_activity) ---
    since_30d = datetime.utcnow() - timedelta(days=30)
    unified_recent = _unified_actions_query(account.id, since_30d)
    res = await session.execute(
        select(unified_recent).order_by(unified_recent.c.time.desc()).limit(10)
    )
    recent = [
        {
            "action_type": r.action_type,
            "status": r.status,
            "time": r.time.isoformat() if r.time else None,
            "category": r.category,
            "source": r.source,
        }
        for r in res.all()
    ]

    # --- follow campaign progress (mirrors analytics.follow_campaign_stats) ---
    counts: dict = {}
    for state in _CAMPAIGN_STATES:
        res = await session.execute(
            select(func.count())
            .select_from(FollowCandidate)
            .where(
                FollowCandidate.account_id == account.id,
                FollowCandidate.status == state,
            )
        )
        counts[state] = res.scalar() or 0
    total = sum(counts.values())
    followed = counts.get("followed", 0)
    campaign = {
        "total": total,
        "followed": followed,
        "remaining": counts.get("queued", 0),
        "failed": counts.get("failed", 0),
        "progress": round(followed / total * 100, 1) if total else 0,
        "counts": counts,
    }

    return {
        "id": account.id,
        "username": account.username,
        "display_name": account.display_name,
        "is_logged_in": account.is_logged_in,
        "is_active": account.is_active,
        "behavior_enabled": account.behavior_enabled,
        "campaign_enabled": account.campaign_enabled,
        "last_session_check": (
            account.last_session_check.isoformat() if account.last_session_check else None
        ),
        "profile": {
            "current": {
                "followers": latest.followers_count if latest else 0,
                "following": latest.following_count if latest else 0,
                "tweets": latest.tweet_count if latest else 0,
            },
            "growth": growth,
            "history": [
                {
                    "date": s.snapshot_date,
                    "followers": s.followers_count,
                    "following": s.following_count,
                    "tweets": s.tweet_count,
                }
                for s in snaps
            ],
        },
        "actions_7d": actions_7d,
        "campaign": campaign,
        "recent": recent,
    }


async def build_snapshot() -> dict:
    """Assemble the full public snapshot from the local database."""
    async with async_session() as session:
        res = await session.execute(select(Account).order_by(Account.created_at))
        accounts = list(res.scalars().all())
        blocks = []
        for account in accounts:
            try:
                blocks.append(await _account_block(session, account))
            except Exception as e:  # one bad account must not sink the whole snapshot
                print(f"[publisher] skipped account {account.username}: {e}", flush=True)

    totals = {
        "accounts": len(blocks),
        "logged_in": sum(1 for b in blocks if b["is_logged_in"]),
        "active": sum(1 for b in blocks if b["is_active"]),
        "total_followers": sum(b["profile"]["current"]["followers"] for b in blocks),
    }
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "refresh_minutes": settings.publish_interval_minutes,
        "totals": totals,
        "accounts": blocks,
    }


async def _put_file(content: str) -> None:
    """Create or update settings.status_path in the public repo via the Contents API."""
    url = f"{GITHUB_API}/repos/{settings.status_repo}/contents/{settings.status_path}"
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")

    async with httpx.AsyncClient(timeout=30) as client:
        # An update requires the current blob SHA; a first-time create does not.
        sha = None
        existing = await client.get(
            url, headers=headers, params={"ref": settings.status_branch}
        )
        if existing.status_code == 200:
            sha = existing.json().get("sha")

        body = {
            "message": f"status update {datetime.utcnow().isoformat()}Z",
            "content": encoded,
            "branch": settings.status_branch,
        }
        if sha:
            body["sha"] = sha

        resp = await client.put(url, headers=headers, json=body)
        resp.raise_for_status()


async def publish() -> bool:
    """Build and push the snapshot. Returns False when publishing is not configured."""
    if not (settings.github_token and settings.status_repo):
        return False
    snapshot = await build_snapshot()
    await _put_file(json.dumps(snapshot, indent=2, default=str))
    return True


async def publish_safe() -> None:
    """Scheduler entrypoint: never raise, just log."""
    try:
        if await publish():
            print("[publisher] status snapshot published", flush=True)
    except Exception as e:
        print(f"[publisher] publish failed: {e}", flush=True)
