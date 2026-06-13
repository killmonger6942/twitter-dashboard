import asyncio
import base64
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import BROWSERS_DIR
from backend.models.database import Account, get_db
from backend.services import browser_service

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AddAccountRequest(BaseModel):
    username: str


class AccountResponse(BaseModel):
    id: str
    username: str
    display_name: str
    persona_id: Optional[str]
    is_logged_in: bool
    is_active: bool
    created_at: str


@router.get("")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).order_by(Account.created_at))
    accounts = result.scalars().all()
    return [
        AccountResponse(
            id=a.id,
            username=a.username,
            display_name=a.display_name or "",
            persona_id=a.persona_id,
            is_logged_in=a.is_logged_in,
            is_active=a.is_active,
            created_at=a.created_at.isoformat() if a.created_at else "",
        )
        for a in accounts
    ]


@router.post("")
async def add_account(req: AddAccountRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Account).where(Account.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Account already exists")

    context_dir = str(BROWSERS_DIR / req.username)
    account = Account(
        username=req.username,
        browser_context_dir=context_dir,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    return AccountResponse(
        id=account.id,
        username=account.username,
        display_name="",
        persona_id=None,
        is_logged_in=False,
        is_active=True,
        created_at=account.created_at.isoformat(),
    )


@router.post("/{account_id}/login")
async def open_login(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    context_dir, context = await browser_service.open_login_browser(account.id, account.username)

    return {
        "message": f"Browser opened for @{account.username}. Log in manually, then call /api/accounts/{account_id}/confirm-login",
        "context_dir": context_dir,
    }


@router.post("/{account_id}/confirm-login")
async def confirm_login(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    await browser_service.save_session(account_id, account.username)
    account.is_logged_in = True
    account.last_session_check = datetime.utcnow()
    await db.commit()

    return {"message": f"@{account.username} session saved", "is_logged_in": True}


@router.get("/{account_id}/screenshot")
async def get_screenshot(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    try:
        if account_id not in browser_service._pages or browser_service._pages[account_id].is_closed():
            await browser_service.navigate(account_id, account.username, "https://x.com")
        b64 = await browser_service.take_screenshot_b64(account_id, account.username)
        return {"screenshot": b64}
    except Exception as e:
        raise HTTPException(500, f"Screenshot failed: {str(e)}")


@router.delete("/{account_id}")
async def delete_account(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    await browser_service.close_context(account_id)
    await db.delete(account)
    await db.commit()
    return {"message": f"@{account.username} removed"}
