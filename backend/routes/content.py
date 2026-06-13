import asyncio
import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import SCREENSHOTS_DIR
from backend.models.database import Account, ContentItem, Persona, async_session, get_db
from backend.services import ai_service, browser_service, computer_use_service

_background_tasks: dict[str, asyncio.Task] = {}

router = APIRouter(prefix="/api/content", tags=["content"])


class CreateContentRequest(BaseModel):
    account_id: str
    content_type: str = "tweet"
    body: str
    target_tweet_url: Optional[str] = None
    scheduled_for: Optional[str] = None


class ContentResponse(BaseModel):
    id: str
    account_id: str
    content_type: str
    status: str
    body: str
    target_tweet_url: Optional[str]
    scheduled_for: Optional[str]
    posted_at: Optional[str]
    error_message: Optional[str]
    screenshot_path: Optional[str]
    created_at: str


def _to_response(c: ContentItem) -> ContentResponse:
    return ContentResponse(
        id=c.id,
        account_id=c.account_id,
        content_type=c.content_type,
        status=c.status,
        body=c.body,
        target_tweet_url=c.target_tweet_url,
        scheduled_for=c.scheduled_for.isoformat() if c.scheduled_for else None,
        posted_at=c.posted_at.isoformat() if c.posted_at else None,
        error_message=c.error_message,
        screenshot_path=c.screenshot_path,
        created_at=c.created_at.isoformat() if c.created_at else "",
    )


@router.get("")
async def list_content(
    account_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ContentItem).order_by(ContentItem.created_at.desc())
    if account_id:
        query = query.where(ContentItem.account_id == account_id)
    if status:
        query = query.where(ContentItem.status == status)
    result = await db.execute(query)
    return [_to_response(c) for c in result.scalars().all()]


@router.post("")
async def create_content(req: CreateContentRequest, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, req.account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    scheduled = None
    if req.scheduled_for:
        scheduled = datetime.fromisoformat(req.scheduled_for)

    item = ContentItem(
        account_id=req.account_id,
        content_type=req.content_type,
        body=req.body,
        target_tweet_url=req.target_tweet_url,
        status="approved" if not scheduled else "scheduled",
        scheduled_for=scheduled,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


class GenerateRequest(BaseModel):
    account_id: str
    direction: Optional[str] = None
    count: int = 3


@router.post("/generate")
async def generate_content(req: GenerateRequest, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, req.account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if not account.persona_id:
        raise HTTPException(400, "Account has no persona assigned")

    persona = await db.get(Persona, account.persona_id)
    if not persona:
        raise HTTPException(404, "Persona not found")

    drafts = await ai_service.generate_tweets(
        system_prompt=persona.system_prompt,
        direction=req.direction,
        count=req.count,
    )

    return {"drafts": drafts, "persona_name": persona.name}


@router.patch("/{content_id}/approve")
async def approve_content(content_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(ContentItem, content_id)
    if not item:
        raise HTTPException(404, "Content not found")
    item.status = "approved"
    await db.commit()
    return _to_response(item)


async def _execute_post(content_id: str, account_id: str, username: str, delay_seconds: int = 0):
    if delay_seconds > 0:
        print(f"[scheduler] Waiting {delay_seconds}s before posting {content_id}", flush=True)
        await asyncio.sleep(delay_seconds)

    print(f"[scheduler] Starting post for {content_id}", flush=True)

    async with async_session() as db:
        item = await db.get(ContentItem, content_id)
        if not item:
            return

        item.status = "posting"
        await db.commit()

        nav_url = item.target_tweet_url or "https://x.com"
        await browser_service.navigate(account_id, username, nav_url)

        try:
            if item.content_type in ("retweet", "like"):
                if item.content_type == "retweet":
                    ok = await browser_service.retweet_first_tweet(account_id, username)
                else:
                    ok = await browser_service.like_first_tweet(account_id, username)

                if ok:
                    item.status = "posted"
                    item.posted_at = datetime.utcnow()
                    screenshot_bytes = await browser_service.take_screenshot(account_id, username)
                    screenshot_path = SCREENSHOTS_DIR / f"{item.id}.png"
                    screenshot_path.write_bytes(screenshot_bytes)
                    item.screenshot_path = str(screenshot_path)
                else:
                    item.status = "failed"
                    item.error_message = "Action failed — element not found"
                result = {"success": ok}
            else:
                task = _build_task_prompt(item)
                result = await computer_use_service.run_task(
                    account_id=account_id,
                    username=username,
                    task_description=task,
                )

                if result["success"]:
                    item.status = "posted"
                    item.posted_at = datetime.utcnow()
                    screenshot_bytes = await browser_service.take_screenshot(account_id, username)
                    screenshot_path = SCREENSHOTS_DIR / f"{item.id}.png"
                    screenshot_path.write_bytes(screenshot_bytes)
                    item.screenshot_path = str(screenshot_path)
                else:
                    item.status = "failed"
                    item.error_message = result.get("message", "Unknown error")

            await db.commit()
            print(f"[scheduler] Post {content_id}: {item.status}", flush=True)

        except Exception as e:
            item.status = "failed"
            item.error_message = str(e)
            await db.commit()
            print(f"[scheduler] Post {content_id} error: {e}", flush=True)
        finally:
            _background_tasks.pop(content_id, None)


@router.post("/{content_id}/post")
async def post_content(
    content_id: str,
    delay: int = 0,
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(ContentItem, content_id)
    if not item:
        raise HTTPException(404, "Content not found")

    account = await db.get(Account, item.account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    if not account.is_logged_in:
        raise HTTPException(400, "Account not logged in")

    if delay > 0:
        item.status = "scheduled"
        await db.commit()
        task = asyncio.create_task(
            _execute_post(content_id, account.id, account.username, delay)
        )
        _background_tasks[content_id] = task
        return {
            "message": f"Post scheduled in {delay} seconds",
            "content_id": content_id,
            "status": "scheduled",
            "delay_seconds": delay,
        }

    await _execute_post(content_id, account.id, account.username)

    await db.refresh(item)
    return _to_response(item)


def _build_task_prompt(item: ContentItem) -> str:
    if item.content_type == "tweet":
        return (
            f"Post the following tweet on Twitter/X:\n\n"
            f'"{item.body}"\n\n'
            f"Steps: Click the compose/post button (the blue + button or the 'Post' area), "
            f"type the tweet text exactly as shown above, then click the Post/Tweet button to publish it. "
            f"Confirm the tweet was posted successfully."
        )
    elif item.content_type == "reply":
        return (
            f"Navigate to this tweet: {item.target_tweet_url}\n"
            f"Then reply with: \"{item.body}\"\n"
            f"Click the reply button, type the reply, and post it."
        )
    elif item.content_type == "like":
        return (
            f"Navigate to this tweet: {item.target_tweet_url}\n"
            f"Click the like/heart button to like it."
        )
    elif item.content_type == "retweet":
        url = item.target_tweet_url
        if url and "/status/" not in url:
            return (
                "You are on a Twitter profile page. "
                "Find the repost/retweet icon on the first tweet you see. "
                "The repost icon looks like two arrows forming a loop. "
                "Click it, then click Repost in the menu that appears."
            )
        return (
            "You are on a tweet page. "
            "Find and click the repost/retweet icon (two arrows forming a loop). "
            "Then click Repost in the menu that appears."
        )
    elif item.content_type == "follow":
        return (
            f"Navigate to this profile: {item.target_tweet_url}\n"
            f"Click the Follow button."
        )
    else:
        return f"Perform this action on Twitter: {item.body}"


@router.get("/{content_id}")
async def get_content(content_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(ContentItem, content_id)
    if not item:
        raise HTTPException(404, "Content not found")
    return _to_response(item)


@router.delete("/{content_id}")
async def delete_content(content_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(ContentItem, content_id)
    if not item:
        raise HTTPException(404, "Content not found")
    await db.delete(item)
    await db.commit()
    return {"message": "Deleted"}
