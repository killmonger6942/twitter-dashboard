from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import (
    Account,
    AnalyticsSnapshot,
    BehaviorLog,
    ContentItem,
    FollowCandidate,
    get_db,
    async_session,
)
from backend.services import browser_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _unified_actions_query(account_id: str, since: datetime):
    behavior_q = (
        select(
            BehaviorLog.action_type.label("action_type"),
            BehaviorLog.status.label("status"),
            BehaviorLog.scheduled_time.label("time"),
            BehaviorLog.category.label("category"),
            BehaviorLog.error_message.label("error_message"),
            literal("engine").label("source"),
        )
        .where(
            BehaviorLog.account_id == account_id,
            BehaviorLog.scheduled_time >= since,
        )
    )

    content_q = (
        select(
            ContentItem.content_type.label("action_type"),
            case(
                (ContentItem.status == "posted", "done"),
                (ContentItem.status == "failed", "failed"),
                else_=ContentItem.status,
            ).label("status"),
            func.coalesce(ContentItem.posted_at, ContentItem.created_at).label("time"),
            literal(None).label("category"),
            ContentItem.error_message.label("error_message"),
            literal("manual").label("source"),
        )
        .where(
            ContentItem.account_id == account_id,
            func.coalesce(ContentItem.posted_at, ContentItem.created_at) >= since,
        )
    )

    return union_all(behavior_q, content_q).subquery()


@router.get("/summary")
async def summary(
    account_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    unified = _unified_actions_query(account_id, since)

    result = await db.execute(
        select(
            unified.c.action_type,
            func.count().label("total"),
            func.sum(case((unified.c.status == "done", 1), else_=0)).label("done"),
            func.sum(case((unified.c.status == "failed", 1), else_=0)).label("failed"),
        )
        .group_by(unified.c.action_type)
    )
    rows = result.all()
    return {
        "days": days,
        "actions": {
            row.action_type: {
                "total": row.total,
                "done": row.done,
                "failed": row.failed,
            }
            for row in rows
        },
    }


@router.get("/timeline")
async def timeline(
    account_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    unified = _unified_actions_query(account_id, since)

    result = await db.execute(
        select(
            func.date(unified.c.time).label("day"),
            unified.c.action_type,
            func.count().label("count"),
        )
        .where(unified.c.status == "done")
        .group_by("day", unified.c.action_type)
        .order_by("day")
    )
    rows = result.all()

    days_map: dict[str, dict] = {}
    for row in rows:
        day = str(row.day)
        if day not in days_map:
            days_map[day] = {"date": day}
        days_map[day][row.action_type] = row.count

    return list(days_map.values())


@router.get("/success-rate")
async def success_rate(
    account_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    unified = _unified_actions_query(account_id, since)

    result = await db.execute(
        select(
            unified.c.action_type,
            unified.c.status,
            func.count().label("count"),
        )
        .where(unified.c.status.in_(["done", "failed"]))
        .group_by(unified.c.action_type, unified.c.status)
    )
    rows = result.all()

    data: dict[str, dict] = {}
    for row in rows:
        if row.action_type not in data:
            data[row.action_type] = {"action_type": row.action_type, "done": 0, "failed": 0}
        data[row.action_type][row.status] = row.count

    return list(data.values())


@router.get("/follow-campaign")
async def follow_campaign_stats(
    account_id: str,
    db: AsyncSession = Depends(get_db),
):
    counts = {}
    for s in ["discovered", "queued", "followed", "following", "skipped", "failed"]:
        result = await db.execute(
            select(func.count())
            .select_from(FollowCandidate)
            .where(
                FollowCandidate.account_id == account_id,
                FollowCandidate.status == s,
            )
        )
        counts[s] = result.scalar() or 0

    total = sum(counts.values())
    followed = counts.get("followed", 0)
    return {
        "total": total,
        "followed": followed,
        "remaining": counts.get("queued", 0),
        "failed": counts.get("failed", 0),
        "progress": round(followed / total * 100, 1) if total > 0 else 0,
        "counts": counts,
    }


@router.get("/recent")
async def recent_activity(
    account_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=30)
    unified = _unified_actions_query(account_id, since)

    result = await db.execute(
        select(unified).order_by(unified.c.time.desc()).limit(limit)
    )
    rows = result.all()
    return [
        {
            "action_type": r.action_type,
            "status": r.status,
            "time": r.time.isoformat() if r.time else None,
            "category": r.category,
            "error_message": r.error_message,
            "source": r.source,
        }
        for r in rows
    ]


@router.get("/profile")
async def profile_metrics(
    account_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.account_id == account_id)
        .order_by(AnalyticsSnapshot.snapshot_date.desc())
        .limit(30)
    )
    snapshots = result.scalars().all()
    snapshots.reverse()

    latest = snapshots[-1] if snapshots else None
    first = snapshots[0] if snapshots else None

    growth = {}
    if latest and first and len(snapshots) > 1:
        growth = {
            "followers": latest.followers_count - first.followers_count,
            "following": latest.following_count - first.following_count,
            "tweets": latest.tweet_count - first.tweet_count,
        }

    return {
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
            for s in snapshots
        ],
    }


@router.post("/profile/snapshot")
async def take_profile_snapshot(
    account_id: str,
    db: AsyncSession = Depends(get_db),
):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if not account.is_logged_in:
        raise HTTPException(400, "Account not logged in")

    stats = await browser_service.scrape_profile_stats(account_id, account.username)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    existing = await db.execute(
        select(AnalyticsSnapshot).where(
            AnalyticsSnapshot.account_id == account_id,
            AnalyticsSnapshot.snapshot_date == today,
        )
    )
    snapshot = existing.scalars().first()

    if snapshot:
        snapshot.followers_count = stats["followers"]
        snapshot.following_count = stats["following"]
        snapshot.tweet_count = stats["tweets"]
    else:
        snapshot = AnalyticsSnapshot(
            account_id=account_id,
            snapshot_date=today,
            followers_count=stats["followers"],
            following_count=stats["following"],
            tweet_count=stats["tweets"],
        )
        db.add(snapshot)

    await db.commit()

    return {
        "date": today,
        "followers": stats["followers"],
        "following": stats["following"],
        "tweets": stats["tweets"],
    }
