from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Account, BehaviorLog, EngagementTarget, FollowCandidate, get_db
from backend.services import behavior_engine, follow_campaign

router = APIRouter(prefix="/api/behavior", tags=["behavior"])


@router.post("/start")
async def start_behavior(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if not account.is_logged_in:
        raise HTTPException(400, "Account not logged in")
    if not account.persona_id:
        raise HTTPException(400, "Account has no persona assigned")

    try:
        engine = await behavior_engine.start_engine(account_id)
        return engine.status()
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/stop")
async def stop_behavior(account_id: str):
    await behavior_engine.stop_engine(account_id)
    return {"message": "Behavior engine stopped"}


@router.get("/status")
async def behavior_status(account_id: Optional[str] = None):
    if account_id:
        engine = behavior_engine.get_engine(account_id)
        if not engine:
            return {"running": False, "account_id": account_id}
        return engine.status()
    return behavior_engine.list_engines()


@router.get("/log")
async def behavior_log(
    account_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BehaviorLog)
        .where(BehaviorLog.account_id == account_id)
        .order_by(BehaviorLog.scheduled_time.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "action_type": l.action_type,
            "category": l.category,
            "status": l.status,
            "scheduled_time": l.scheduled_time.isoformat() if l.scheduled_time else None,
            "executed_at": l.executed_at.isoformat() if l.executed_at else None,
            "error_message": l.error_message,
        }
        for l in logs
    ]


class AddTargetRequest(BaseModel):
    account_id: str
    target_username: str
    category: str = "ai"
    priority: int = 5


@router.post("/targets")
async def add_target(req: AddTargetRequest, db: AsyncSession = Depends(get_db)):
    target = EngagementTarget(
        account_id=req.account_id,
        target_username=req.target_username.lstrip("@"),
        category=req.category,
        priority=req.priority,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return {
        "id": target.id,
        "target_username": target.target_username,
        "category": target.category,
        "priority": target.priority,
    }


@router.get("/targets")
async def list_targets(account_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EngagementTarget)
        .where(EngagementTarget.account_id == account_id)
        .order_by(EngagementTarget.priority.desc())
    )
    targets = result.scalars().all()
    return [
        {
            "id": t.id,
            "target_username": t.target_username,
            "category": t.category,
            "priority": t.priority,
            "last_engaged": t.last_engaged.isoformat() if t.last_engaged else None,
        }
        for t in targets
    ]


@router.delete("/targets/{target_id}")
async def delete_target(target_id: str, db: AsyncSession = Depends(get_db)):
    target = await db.get(EngagementTarget, target_id)
    if not target:
        raise HTTPException(404, "Target not found")
    await db.delete(target)
    await db.commit()
    return {"message": "Target removed"}


# --- Follow Campaign ---


class DiscoverRequest(BaseModel):
    account_id: str
    seed_accounts: Optional[list[str]] = None
    target_count: int = 275


@router.post("/follow-campaign/discover")
async def discover_candidates(req: DiscoverRequest, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, req.account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if not account.is_logged_in:
        raise HTTPException(400, "Account not logged in")

    campaign = await follow_campaign.start_campaign(
        account_id=account.id,
        username=account.username,
        seed_accounts=req.seed_accounts,
        target_count=req.target_count,
    )
    import asyncio
    asyncio.create_task(campaign.discover())
    return {
        "message": "Discovery started in background",
        "seed_accounts": campaign.seed_accounts,
        "target_count": campaign.target_count,
    }


@router.post("/follow-campaign/start")
async def start_follow_campaign(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    campaign = follow_campaign.get_campaign(account_id)
    if not campaign:
        campaign = await follow_campaign.start_campaign(
            account_id=account.id,
            username=account.username,
        )

    await campaign.start_following()
    await follow_campaign.set_campaign_enabled(account_id, True)
    return await campaign.status()


@router.post("/follow-campaign/stop")
async def stop_follow_campaign(account_id: str):
    await follow_campaign.stop_campaign(account_id)
    return {"message": "Follow campaign stopped"}


@router.get("/follow-campaign/status")
async def follow_campaign_status(account_id: str):
    campaign = follow_campaign.get_campaign(account_id)
    if not campaign:
        return {"running": False, "account_id": account_id}
    return await campaign.status()


@router.get("/follow-campaign/candidates")
async def list_candidates(
    account_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(FollowCandidate)
        .where(FollowCandidate.account_id == account_id)
        .order_by(FollowCandidate.times_seen.desc())
        .limit(limit)
    )
    if status:
        query = query.where(FollowCandidate.status == status)
    result = await db.execute(query)
    candidates = result.scalars().all()
    return [
        {
            "id": c.id,
            "target_username": c.target_username,
            "display_name": c.display_name,
            "bio": c.bio[:100] if c.bio else "",
            "times_seen": c.times_seen,
            "status": c.status,
            "source_seed": c.source_seed,
            "followed_at": c.followed_at.isoformat() if c.followed_at else None,
        }
        for c in candidates
    ]
