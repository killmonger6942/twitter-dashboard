import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func

from backend.config import settings
from backend.models.database import Account, FollowCandidate, async_session
from backend.scheduler import scheduler
from backend.services import browser_service

_campaigns: dict[str, "FollowCampaign"] = {}

DEFAULT_SEEDS = [
    "karpathy",
    "jeremyphoward",
    "swyx",
    "simonw",
    "hwchase17",
    "jxnlco",
    "AIatMeta",
    "GoogleDeepMind",
    "huggingface",
    "LangChainAI",
]

ACTIVE_WINDOWS = [
    (8, 0, 10, 30),
    (12, 0, 14, 0),
    (15, 30, 17, 30),
    (19, 30, 22, 0),
]


class FollowCampaign:
    def __init__(
        self,
        account_id: str,
        username: str,
        seed_accounts: list[str],
        target_count: int = 275,
    ):
        self.account_id = account_id
        self.username = username
        self.seed_accounts = seed_accounts
        self.target_count = target_count
        self.running = False
        self.discovering = False
        self._job_ids: list[str] = []
        self._discover_task: Optional[asyncio.Task] = None

    async def discover(self):
        self.discovering = True
        total_discovered = 0

        for seed in self.seed_accounts:
            if not self.discovering:
                break
            print(f"[follow-campaign] Scraping @{seed}/following...", flush=True)
            try:
                users = await browser_service.scrape_following_list(
                    self.account_id, self.username, seed, max_scroll=30
                )
            except Exception as e:
                print(f"[follow-campaign] Failed to scrape @{seed}: {e}", flush=True)
                continue

            async with async_session() as db:
                for u in users:
                    if u["username"].lower() == self.username.lower():
                        continue

                    existing = await db.execute(
                        select(FollowCandidate).where(
                            FollowCandidate.account_id == self.account_id,
                            FollowCandidate.target_username == u["username"],
                        )
                    )
                    candidate = existing.scalars().first()

                    if candidate:
                        candidate.times_seen += 1
                        if seed not in (candidate.source_seed or ""):
                            candidate.source_seed += f",{seed}"
                    else:
                        candidate = FollowCandidate(
                            account_id=self.account_id,
                            target_username=u["username"],
                            display_name=u.get("display_name", ""),
                            bio=u.get("bio", ""),
                            source_seed=seed,
                            times_seen=1,
                            status="discovered",
                        )
                        db.add(candidate)
                        total_discovered += 1

                await db.commit()

            print(
                f"[follow-campaign] Done with @{seed} — {len(users)} users found",
                flush=True,
            )
            await asyncio.sleep(5)

        await self._queue_top_candidates()
        self.discovering = False
        print(
            f"[follow-campaign] Discovery complete — {total_discovered} unique candidates",
            flush=True,
        )

    async def _queue_top_candidates(self):
        async with async_session() as db:
            result = await db.execute(
                select(FollowCandidate)
                .where(
                    FollowCandidate.account_id == self.account_id,
                    FollowCandidate.status == "discovered",
                )
                .order_by(FollowCandidate.times_seen.desc())
                .limit(self.target_count)
            )
            candidates = result.scalars().all()
            for c in candidates:
                c.status = "queued"
            await db.commit()
            print(
                f"[follow-campaign] Queued {len(candidates)} candidates for following",
                flush=True,
            )

    async def start_following(self):
        self.running = True
        job_id = f"follow_campaign_{self.account_id}"
        scheduler.add_job(
            _run_daily_follows,
            "cron",
            hour=8,
            minute=15,
            args=[self.account_id],
            id=job_id,
            replace_existing=True,
        )
        self._job_ids.append(job_id)

        await self._schedule_today()
        print(f"[follow-campaign] Started for @{self.username}", flush=True)

    async def _schedule_today(self):
        async with async_session() as db:
            result = await db.execute(
                select(func.count())
                .select_from(FollowCandidate)
                .where(
                    FollowCandidate.account_id == self.account_id,
                    FollowCandidate.status == "queued",
                )
            )
            remaining = result.scalar() or 0

        if remaining == 0:
            print("[follow-campaign] No more candidates — campaign complete", flush=True)
            await self.stop()
            return

        daily_count = min(
            random.randint(
                settings.follow_campaign_daily_min,
                settings.follow_campaign_daily_max,
            ),
            remaining,
        )

        now = datetime.now()
        times = []
        for window in ACTIVE_WINDOWS:
            start_h, start_m, end_h, end_m = window
            start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            if end <= now:
                continue
            if start < now:
                start = now + timedelta(minutes=2)
            delta = (end - start).total_seconds()
            if delta > 0:
                times.append((start, end))

        if not times:
            print("[follow-campaign] No active windows remaining today", flush=True)
            return

        follow_times = []
        for _ in range(daily_count):
            window_start, window_end = random.choice(times)
            delta = (window_end - window_start).total_seconds()
            offset = random.uniform(0, delta * 0.9)
            follow_times.append(window_start + timedelta(seconds=offset))

        follow_times.sort()

        gap_min = settings.follow_campaign_gap_min
        gap_max = settings.follow_campaign_gap_max
        for i in range(1, len(follow_times)):
            diff = (follow_times[i] - follow_times[i - 1]).total_seconds()
            if diff < gap_min:
                gap = random.randint(gap_min, gap_max)
                follow_times[i] = follow_times[i - 1] + timedelta(seconds=gap)

        for t in follow_times:
            job_id = f"campaign_follow_{self.account_id}_{t.timestamp()}"
            scheduler.add_job(
                _execute_follow,
                "date",
                run_date=t,
                args=[self.account_id],
                id=job_id,
                replace_existing=True,
            )
            self._job_ids.append(job_id)

        print(
            f"[follow-campaign] Scheduled {len(follow_times)} follows today "
            f"({remaining} remaining)",
            flush=True,
        )

    async def stop(self):
        self.running = False
        self.discovering = False
        for job_id in self._job_ids:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass
        self._job_ids.clear()
        print(f"[follow-campaign] Stopped for @{self.username}", flush=True)

    async def status(self) -> dict:
        async with async_session() as db:
            counts = {}
            for s in ["discovered", "queued", "followed", "skipped", "failed"]:
                result = await db.execute(
                    select(func.count())
                    .select_from(FollowCandidate)
                    .where(
                        FollowCandidate.account_id == self.account_id,
                        FollowCandidate.status == s,
                    )
                )
                counts[s] = result.scalar() or 0

        return {
            "running": self.running,
            "discovering": self.discovering,
            "account_id": self.account_id,
            "username": self.username,
            "seed_accounts": self.seed_accounts,
            "target_count": self.target_count,
            "counts": counts,
        }


async def _run_daily_follows(account_id: str):
    campaign = _campaigns.get(account_id)
    if campaign and campaign.running:
        await campaign._schedule_today()


async def _execute_follow(account_id: str):
    campaign = _campaigns.get(account_id)
    if not campaign or not campaign.running:
        return

    async with async_session() as db:
        result = await db.execute(
            select(FollowCandidate)
            .where(
                FollowCandidate.account_id == account_id,
                FollowCandidate.status == "queued",
            )
            .order_by(FollowCandidate.times_seen.desc())
            .limit(1)
        )
        candidate = result.scalars().first()
        if not candidate:
            return

        candidate.status = "following"
        await db.commit()

        try:
            url = f"https://x.com/{candidate.target_username}"
            await browser_service.navigate(
                account_id, campaign.username, url
            )
            await asyncio.sleep(2)
            ok = await browser_service.follow_user(account_id, campaign.username)

            if ok:
                candidate.status = "followed"
                candidate.followed_at = datetime.utcnow()
                print(
                    f"[follow-campaign] Followed @{candidate.target_username}",
                    flush=True,
                )
            else:
                candidate.status = "failed"
                print(
                    f"[follow-campaign] Failed to follow @{candidate.target_username}",
                    flush=True,
                )
        except Exception as e:
            candidate.status = "failed"
            print(
                f"[follow-campaign] Error following @{candidate.target_username}: {e}",
                flush=True,
            )

        await db.commit()


async def start_campaign(
    account_id: str,
    username: str,
    seed_accounts: Optional[list[str]] = None,
    target_count: int = 275,
) -> FollowCampaign:
    if account_id in _campaigns and _campaigns[account_id].running:
        return _campaigns[account_id]

    seeds = seed_accounts or DEFAULT_SEEDS
    campaign = FollowCampaign(account_id, username, seeds, target_count)
    _campaigns[account_id] = campaign
    return campaign


async def stop_campaign(account_id: str):
    campaign = _campaigns.pop(account_id, None)
    if campaign:
        await campaign.stop()

    async with async_session() as db:
        account = await db.get(Account, account_id)
        if account:
            account.campaign_enabled = False
            await db.commit()


async def set_campaign_enabled(account_id: str, enabled: bool):
    async with async_session() as db:
        account = await db.get(Account, account_id)
        if account:
            account.campaign_enabled = enabled
            await db.commit()


async def auto_recover_campaigns():
    async with async_session() as db:
        result = await db.execute(
            select(Account).where(
                Account.campaign_enabled == True,
                Account.is_logged_in == True,
            )
        )
        accounts = result.scalars().all()

    for account in accounts:
        async with async_session() as db:
            remaining = await db.execute(
                select(func.count())
                .select_from(FollowCandidate)
                .where(
                    FollowCandidate.account_id == account.id,
                    FollowCandidate.status == "queued",
                )
            )
            queued_count = remaining.scalar() or 0

        if queued_count == 0:
            await set_campaign_enabled(account.id, False)
            print(
                f"[recovery] Campaign for @{account.username} complete — no queued candidates",
                flush=True,
            )
            continue

        try:
            campaign = await start_campaign(account.id, account.username)
            await campaign.start_following()
            print(
                f"[recovery] Auto-resumed follow campaign for @{account.username} "
                f"({queued_count} remaining)",
                flush=True,
            )
        except Exception as e:
            print(
                f"[recovery] Failed to resume campaign for @{account.username}: {e}",
                flush=True,
            )


def get_campaign(account_id: str) -> Optional[FollowCampaign]:
    return _campaigns.get(account_id)
