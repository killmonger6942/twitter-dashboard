from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Account, get_db
from backend.services import monitor_service

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


class StartMonitorRequest(BaseModel):
    account_id: str
    target_username: str
    retweet_delay: int = 300
    check_interval: int = 120


@router.post("/start")
async def start_monitor(req: StartMonitorRequest, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, req.account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if not account.is_logged_in:
        raise HTTPException(400, "Account not logged in")

    monitor = await monitor_service.start_monitor(
        account_id=account.id,
        username=account.username,
        target_username=req.target_username.lstrip("@"),
        retweet_delay=req.retweet_delay,
        check_interval=req.check_interval,
    )
    return monitor.status()


@router.post("/stop")
async def stop_monitor(account_id: str, target_username: str):
    await monitor_service.stop_monitor(account_id, target_username.lstrip("@"))
    return {"message": "Monitor stopped"}


@router.get("")
async def list_monitors():
    return monitor_service.list_monitors()
