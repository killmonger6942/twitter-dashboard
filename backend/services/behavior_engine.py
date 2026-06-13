import asyncio
import random
import uuid
from datetime import datetime, timedelta
from typing import Optional

from backend.config import settings
from sqlalchemy import select

from backend.models.database import (
    Account,
    AnalyticsSnapshot,
    BehaviorLog,
    ContentItem,
    EngagementTarget,
    Persona,
    async_session,
)
from backend.scheduler import scheduler
from backend.services import ai_service, browser_service

_engines: dict[str, "BehaviorEngine"] = {}

ACTIVE_WINDOWS = [
    (8, 0, 10, 30),
    (12, 0, 14, 0),
    (15, 30, 17, 30),
    (19, 30, 22, 0),
]

ACTION_TYPES = ["tweet", "like", "retweet", "reply", "follow"]


class BehaviorEngine:
    def __init__(
        self,
        account_id: str,
        username: str,
        persona_system_prompt: str,
    ):
        self.account_id = account_id
        self.username = username
        self.persona_system_prompt = persona_system_prompt
        self.running = False
        self.today_plan: list[dict] = []
        self.recent_categories: list[str] = []
        self.consecutive_failures = 0
        self._job_ids: list[str] = []

    async def start(self):
        self.running = True
        job_id = f"daily_planner_{self.account_id}"
        scheduler.add_job(
            _run_daily_plan,
            "cron",
            hour=7,
            minute=0,
            args=[self.account_id],
            id=job_id,
            replace_existing=True,
        )
        self._job_ids.append(job_id)

        keepalive_id = f"keepalive_{self.account_id}"
        scheduler.add_job(
            _run_keepalive,
            "interval",
            hours=4,
            args=[self.account_id, self.username],
            id=keepalive_id,
            replace_existing=True,
        )
        self._job_ids.append(keepalive_id)

        await self.generate_daily_plan()
        print(
            f"[behavior] Engine started for @{self.username} — "
            f"{len(self.today_plan)} actions planned",
            flush=True,
        )

    async def stop(self):
        self.running = False
        for job_id in self._job_ids:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
        self._job_ids.clear()
        self.today_plan.clear()
        print(f"[behavior] Engine stopped for @{self.username}", flush=True)

    async def generate_daily_plan(self):
        self.today_plan.clear()
        for job_id in list(self._job_ids):
            if job_id.startswith("action_"):
                try:
                    scheduler.remove_job(job_id)
                except Exception:
                    pass
                self._job_ids.remove(job_id)

        now = datetime.now()
        is_weekend = now.weekday() >= 5
        modifier = settings.behavior_weekend_modifier if is_weekend else 1.0

        counts = {
            "tweet": _rand_count(settings.behavior_tweets_min, settings.behavior_tweets_max, modifier),
            "like": _rand_count(settings.behavior_likes_min, settings.behavior_likes_max, modifier),
            "retweet": _rand_count(settings.behavior_retweets_min, settings.behavior_retweets_max, modifier),
            "reply": _rand_count(settings.behavior_replies_min, settings.behavior_replies_max, modifier),
            "follow": _rand_count(settings.behavior_follows_min, settings.behavior_follows_max, modifier),
        }

        actions = []
        for action_type, count in counts.items():
            for _ in range(count):
                scheduled_time = _random_time_in_window(now)
                if scheduled_time is None:
                    continue
                category = None
                if action_type == "tweet":
                    category = _pick_category(self.recent_categories)
                actions.append({
                    "id": str(uuid.uuid4()),
                    "action_type": action_type,
                    "category": category,
                    "scheduled_time": scheduled_time,
                })

        actions.sort(key=lambda a: a["scheduled_time"])
        actions = _enforce_min_gap(actions, settings.behavior_min_action_gap)

        async with async_session() as db:
            for action in actions:
                log = BehaviorLog(
                    id=action["id"],
                    account_id=self.account_id,
                    action_type=action["action_type"],
                    category=action.get("category"),
                    status="pending",
                    scheduled_time=action["scheduled_time"],
                )
                db.add(log)
            await db.commit()

        for action in actions:
            if action["scheduled_time"] <= now:
                continue
            job_id = f"action_{action['id']}"
            scheduler.add_job(
                _run_action,
                "date",
                run_date=action["scheduled_time"],
                args=[self.account_id, action["id"]],
                id=job_id,
                replace_existing=True,
            )
            self._job_ids.append(job_id)

        self.today_plan = actions
        print(
            f"[behavior] Plan for @{self.username}: "
            f"{counts} (weekend={is_weekend}), "
            f"{len([a for a in actions if a['scheduled_time'] > now])} actions scheduled",
            flush=True,
        )

    async def execute_action(self, action_id: str):
        if not self.running:
            return

        if self.consecutive_failures >= 3:
            print(
                f"[behavior] Engine paused for @{self.username} — "
                f"3 consecutive failures",
                flush=True,
            )
            return

        async with async_session() as db:
            log = await db.get(BehaviorLog, action_id)
            if not log or log.status != "pending":
                return

            log.status = "executing"
            await db.commit()

            try:
                success = await self._dispatch(log.action_type, log.category)
                log.status = "done" if success else "failed"
                log.executed_at = datetime.utcnow()
                if not success:
                    log.error_message = "Action returned false"
                    self.consecutive_failures += 1
                else:
                    self.consecutive_failures = 0
                    if log.category:
                        self.recent_categories.append(log.category)
                        if len(self.recent_categories) > 3:
                            self.recent_categories.pop(0)
            except Exception as e:
                log.status = "failed"
                log.executed_at = datetime.utcnow()
                log.error_message = str(e)[:500]
                self.consecutive_failures += 1
                print(f"[behavior] Action {action_id} error: {e}", flush=True)

            await db.commit()
            print(
                f"[behavior] @{self.username} {log.action_type}"
                f"({log.category or ''}) → {log.status}",
                flush=True,
            )

    async def _dispatch(self, action_type: str, category: Optional[str] = None) -> bool:
        if action_type == "tweet":
            return await self._do_tweet(category or "observation")
        elif action_type == "like":
            return await self._do_like()
        elif action_type == "retweet":
            return await self._do_retweet()
        elif action_type == "reply":
            return await self._do_reply()
        elif action_type == "follow":
            return await self._do_follow()
        return False

    async def _do_tweet(self, category: str) -> bool:
        text = await ai_service.generate_categorized_tweet(
            self.persona_system_prompt, category
        )
        if not text:
            return False

        async with async_session() as db:
            item = ContentItem(
                account_id=self.account_id,
                content_type="tweet",
                body=text,
                status="approved",
            )
            db.add(item)
            await db.commit()
            await db.refresh(item)
            content_id = item.id

        await browser_service.navigate(self.account_id, self.username, "https://x.com")
        from backend.services import computer_use_service

        result = await computer_use_service.run_task(
            account_id=self.account_id,
            username=self.username,
            task_description=(
                f"Post the following tweet on Twitter/X:\n\n"
                f'"{text}"\n\n'
                f"Steps: Click the compose/post button, type the tweet text exactly, "
                f"then click the Post button to publish it."
            ),
        )
        async with async_session() as db:
            item = await db.get(ContentItem, content_id)
            if item:
                item.status = "posted" if result["success"] else "failed"
                item.posted_at = datetime.utcnow() if result["success"] else None
                await db.commit()

        return result["success"]

    async def _do_like(self) -> bool:
        target = await self._pick_target()
        if target:
            url = f"https://x.com/{target}"
        else:
            url = "https://x.com/home"

        await browser_service.navigate(self.account_id, self.username, url)
        await asyncio.sleep(2)
        await browser_service.scroll_random(self.account_id, self.username)
        await asyncio.sleep(1)

        n = random.randint(0, 3)
        return await browser_service.like_nth_tweet(self.account_id, self.username, n)

    async def _do_retweet(self) -> bool:
        target = await self._pick_target()
        if target:
            url = f"https://x.com/{target}"
        else:
            url = "https://x.com/home"

        await browser_service.navigate(self.account_id, self.username, url)
        await asyncio.sleep(2)

        n = random.randint(0, 2)
        return await browser_service.retweet_nth_tweet(self.account_id, self.username, n)

    async def _do_reply(self) -> bool:
        target = await self._pick_target()
        if not target:
            return False

        url = f"https://x.com/{target}"
        await browser_service.navigate(self.account_id, self.username, url)
        await asyncio.sleep(2)

        tweets = await browser_service.get_visible_tweets(self.account_id, self.username)
        if not tweets:
            return False

        tweet = tweets[0]
        reply_text = await ai_service.generate_reply(
            self.persona_system_prompt,
            tweet["text"],
            tweet["author"],
        )
        if not reply_text:
            return False

        page = await browser_service.get_page(self.account_id, self.username)
        try:
            tweet_el = page.locator('[data-testid="tweet"]').first
            reply_btn = tweet_el.locator('[data-testid="reply"]')
            await reply_btn.wait_for(state="visible", timeout=10000)
            await reply_btn.click()
            await asyncio.sleep(1)

            reply_box = page.locator('[data-testid="tweetTextarea_0"]').first
            await reply_box.wait_for(state="visible", timeout=10000)
            await reply_box.click()
            await asyncio.sleep(0.5)
            await page.keyboard.type(reply_text, delay=30)
            await asyncio.sleep(0.5)

            post_btn = page.locator('[data-testid="tweetButton"]')
            await post_btn.wait_for(state="visible", timeout=5000)
            await post_btn.click()
            await asyncio.sleep(2)
            return True
        except Exception as e:
            print(f"[behavior] reply failed: {e}", flush=True)
            return False

    async def _do_follow(self) -> bool:
        target = await self._pick_target()
        if not target:
            return False

        url = f"https://x.com/{target}"
        await browser_service.navigate(self.account_id, self.username, url)
        await asyncio.sleep(2)
        return await browser_service.follow_user(self.account_id, self.username)

    async def _pick_target(self) -> Optional[str]:
        async with async_session() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(EngagementTarget)
                .where(EngagementTarget.account_id == self.account_id)
                .order_by(EngagementTarget.priority.desc())
            )
            targets = result.scalars().all()

        if not targets:
            return None

        weights = [t.priority for t in targets]
        chosen = random.choices(targets, weights=weights, k=1)[0]

        async with async_session() as db:
            target = await db.get(EngagementTarget, chosen.id)
            if target:
                target.last_engaged = datetime.utcnow()
                await db.commit()

        return chosen.target_username

    def status(self) -> dict:
        now = datetime.now()
        pending = [a for a in self.today_plan if a["scheduled_time"] > now]
        done = [a for a in self.today_plan if a["scheduled_time"] <= now]
        return {
            "running": self.running,
            "account_id": self.account_id,
            "username": self.username,
            "total_planned": len(self.today_plan),
            "pending": len(pending),
            "executed": len(done),
            "consecutive_failures": self.consecutive_failures,
            "next_action": _format_action(pending[0]) if pending else None,
            "plan": [_format_action(a) for a in self.today_plan],
        }


def _format_action(action: dict) -> dict:
    return {
        "id": action["id"],
        "action_type": action["action_type"],
        "category": action.get("category"),
        "scheduled_time": action["scheduled_time"].isoformat(),
    }


def _rand_count(min_val: int, max_val: int, modifier: float) -> int:
    count = random.randint(min_val, max_val)
    return max(0, round(count * modifier))


def _random_time_in_window(today: datetime) -> Optional[datetime]:
    window = random.choice(ACTIVE_WINDOWS)
    start_h, start_m, end_h, end_m = window
    start = today.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = today.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    delta = (end - start).total_seconds()
    offset = random.uniform(0, delta * 0.9)
    return start + timedelta(seconds=offset)


def _pick_category(recent: list[str]) -> str:
    categories = list(ai_service.TWEET_CATEGORIES.keys())
    available = [c for c in categories if c not in recent[-2:]]
    if not available:
        available = categories
    return random.choice(available)


def _enforce_min_gap(actions: list[dict], min_gap: int) -> list[dict]:
    if not actions:
        return actions
    result = [actions[0]]
    for action in actions[1:]:
        prev_time = result[-1]["scheduled_time"]
        if (action["scheduled_time"] - prev_time).total_seconds() < min_gap:
            gap = random.randint(min_gap, min_gap + 120)
            action["scheduled_time"] = prev_time + timedelta(seconds=gap)
        result.append(action)
    return result


async def _run_daily_plan(account_id: str):
    engine = _engines.get(account_id)
    if engine and engine.running:
        await engine.generate_daily_plan()


async def _run_action(account_id: str, action_id: str):
    engine = _engines.get(account_id)
    if engine and engine.running:
        await engine.execute_action(action_id)


async def _run_keepalive(account_id: str, username: str):
    try:
        await browser_service.navigate(account_id, username, "https://x.com")
        await browser_service.save_session(account_id, username)
        print(f"[behavior] Session keepalive for @{username}", flush=True)
    except Exception as e:
        print(f"[behavior] Keepalive failed for @{username}: {e}", flush=True)

    try:
        stats = await browser_service.scrape_profile_stats(account_id, username)
        today = datetime.now().strftime("%Y-%m-%d")
        async with async_session() as db:
            existing = await db.execute(
                select(AnalyticsSnapshot).where(
                    AnalyticsSnapshot.account_id == account_id,
                    AnalyticsSnapshot.snapshot_date == today,
                )
            )
            snap = existing.scalars().first()
            if snap:
                snap.followers_count = stats["followers"]
                snap.following_count = stats["following"]
                snap.tweet_count = stats["tweets"]
            else:
                db.add(AnalyticsSnapshot(
                    account_id=account_id,
                    snapshot_date=today,
                    followers_count=stats["followers"],
                    following_count=stats["following"],
                    tweet_count=stats["tweets"],
                ))
            await db.commit()
        print(f"[behavior] Profile snapshot saved for @{username}", flush=True)
    except Exception as e:
        print(f"[behavior] Profile snapshot failed for @{username}: {e}", flush=True)


async def start_engine(account_id: str) -> BehaviorEngine:
    if account_id in _engines and _engines[account_id].running:
        return _engines[account_id]

    async with async_session() as db:
        account = await db.get(Account, account_id)
        if not account:
            raise ValueError("Account not found")
        if not account.persona_id:
            raise ValueError("Account has no persona assigned")
        persona = await db.get(Persona, account.persona_id)
        if not persona:
            raise ValueError("Persona not found")

        account.behavior_enabled = True
        await db.commit()

        engine = BehaviorEngine(
            account_id=account.id,
            username=account.username,
            persona_system_prompt=persona.system_prompt,
        )

    await engine.start()
    _engines[account_id] = engine
    return engine


async def stop_engine(account_id: str):
    engine = _engines.pop(account_id, None)
    if engine:
        await engine.stop()

    async with async_session() as db:
        account = await db.get(Account, account_id)
        if account:
            account.behavior_enabled = False
            await db.commit()


async def auto_recover():
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(Account).where(
                Account.behavior_enabled == True,
                Account.is_logged_in == True,
            )
        )
        accounts = result.scalars().all()

    for account in accounts:
        try:
            await start_engine(account.id)
            print(f"[recovery] Auto-started engine for @{account.username}", flush=True)
        except Exception as e:
            print(f"[recovery] Failed to start engine for @{account.username}: {e}", flush=True)


def get_engine(account_id: str) -> Optional[BehaviorEngine]:
    return _engines.get(account_id)


def list_engines() -> list[dict]:
    return [e.status() for e in _engines.values()]
