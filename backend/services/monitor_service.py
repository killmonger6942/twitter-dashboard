import asyncio
from datetime import datetime
from typing import Optional

from backend.services import browser_service

_monitors: dict[str, "TweetMonitor"] = {}


class TweetMonitor:
    def __init__(
        self,
        account_id: str,
        username: str,
        target_username: str,
        retweet_delay: int = 300,
        check_interval: int = 120,
    ):
        self.account_id = account_id
        self.username = username
        self.target_username = target_username
        self.retweet_delay = retweet_delay
        self.check_interval = check_interval
        self.seen_tweets: set[str] = set()
        self.retweeted: list[dict] = []
        self.running = False
        self.last_check: Optional[datetime] = None
        self._page = None
        self._task = None

    async def start(self):
        self.running = True
        context = await browser_service.get_context(self.account_id, self.username)
        self._page = await context.new_page()

        await self._page.goto(
            f"https://x.com/{self.target_username}",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(3)

        self.seen_tweets = await self._get_tweet_ids()
        self.last_check = datetime.utcnow()

        print(
            f"[monitor] Watching @{self.target_username} — "
            f"{len(self.seen_tweets)} existing tweets, "
            f"check every {self.check_interval}s, "
            f"retweet after {self.retweet_delay}s",
            flush=True,
        )
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        if self._page and not self._page.is_closed():
            await self._page.close()
        print(f"[monitor] Stopped watching @{self.target_username}", flush=True)

    async def _get_tweet_ids(self) -> set:
        try:
            ids = await self._page.evaluate("""() => {
                const ids = new Set();
                document.querySelectorAll('a[href*="/status/"]').forEach(a => {
                    const m = a.href.match(/\\/status\\/(\\d+)/);
                    if (m) ids.add(m[1]);
                });
                return [...ids];
            }""")
            return set(ids)
        except Exception:
            return self.seen_tweets

    async def _poll_loop(self):
        while self.running:
            await asyncio.sleep(self.check_interval)
            if not self.running:
                break
            try:
                await self._page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(5)
                current = await self._get_tweet_ids()
                new_tweets = current - self.seen_tweets
                self.seen_tweets |= current
                self.last_check = datetime.utcnow()

                if new_tweets:
                    print(
                        f"[monitor] {len(new_tweets)} new tweet(s) from "
                        f"@{self.target_username}: {new_tweets}",
                        flush=True,
                    )
                    for tweet_id in new_tweets:
                        asyncio.create_task(self._delayed_retweet(tweet_id))
            except Exception as e:
                print(f"[monitor] Poll error: {e}", flush=True)

    async def _delayed_retweet(self, tweet_id: str):
        print(
            f"[monitor] Tweet {tweet_id} — retweeting in {self.retweet_delay}s",
            flush=True,
        )
        await asyncio.sleep(self.retweet_delay)
        if not self.running:
            return

        context = await browser_service.get_context(self.account_id, self.username)
        rt_page = await context.new_page()
        try:
            await rt_page.goto(
                f"https://x.com/{self.target_username}/status/{tweet_id}",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(2)

            retweet_btn = rt_page.locator('[data-testid="retweet"]').first
            await retweet_btn.wait_for(state="visible", timeout=10000)
            await retweet_btn.click()
            await asyncio.sleep(1)

            confirm_btn = rt_page.locator('[data-testid="retweetConfirm"]')
            await confirm_btn.wait_for(state="visible", timeout=5000)
            await confirm_btn.click()
            await asyncio.sleep(1)

            self.retweeted.append({
                "tweet_id": tweet_id,
                "retweeted_at": datetime.utcnow().isoformat(),
            })
            print(f"[monitor] Retweeted {tweet_id}", flush=True)
        except Exception as e:
            print(f"[monitor] Retweet failed for {tweet_id}: {e}", flush=True)
        finally:
            if not rt_page.is_closed():
                await rt_page.close()

    def status(self) -> dict:
        return {
            "running": self.running,
            "target": f"@{self.target_username}",
            "seen_count": len(self.seen_tweets),
            "retweeted": self.retweeted,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "check_interval": self.check_interval,
            "retweet_delay": self.retweet_delay,
        }


async def start_monitor(
    account_id: str,
    username: str,
    target_username: str,
    retweet_delay: int = 300,
    check_interval: int = 120,
) -> TweetMonitor:
    key = f"{account_id}:{target_username}"
    if key in _monitors and _monitors[key].running:
        return _monitors[key]

    monitor = TweetMonitor(
        account_id, username, target_username, retweet_delay, check_interval
    )
    await monitor.start()
    _monitors[key] = monitor
    return monitor


async def stop_monitor(account_id: str, target_username: str):
    key = f"{account_id}:{target_username}"
    if key in _monitors:
        await _monitors[key].stop()
        del _monitors[key]


def get_monitor(account_id: str, target_username: str) -> Optional[TweetMonitor]:
    return _monitors.get(f"{account_id}:{target_username}")


def list_monitors() -> list[dict]:
    return [{"key": k, **m.status()} for k, m in _monitors.items()]
