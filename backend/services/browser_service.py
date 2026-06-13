from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from backend.config import BROWSERS_DIR, settings

_playwright = None
_browser: Optional[Browser] = None
_contexts: dict[str, BrowserContext] = {}
_pages: dict[str, Page] = {}


async def _ensure_browser():
    global _playwright, _browser
    if _browser is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
    return _browser


async def get_context(account_id: str, username: str) -> BrowserContext:
    if account_id in _contexts:
        return _contexts[account_id]

    browser = await _ensure_browser()
    context_dir = BROWSERS_DIR / username
    context_dir.mkdir(parents=True, exist_ok=True)

    context = await browser.new_context(
        storage_state=str(context_dir / "state.json") if (context_dir / "state.json").exists() else None,
        viewport={"width": settings.display_width, "height": settings.display_height},
        locale="en-US",
        timezone_id="America/New_York",
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)
    _contexts[account_id] = context
    return context


async def get_page(account_id: str, username: str) -> Page:
    if account_id in _pages:
        page = _pages[account_id]
        if not page.is_closed():
            return page

    context = await get_context(account_id, username)
    page = await context.new_page()
    _pages[account_id] = page
    return page


async def navigate(account_id: str, username: str, url: str):
    page = await get_page(account_id, username)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)


async def take_screenshot(account_id: str, username: str) -> bytes:
    page = await get_page(account_id, username)
    return await page.screenshot(type="png")


async def take_screenshot_b64(account_id: str, username: str) -> str:
    png_bytes = await take_screenshot(account_id, username)
    return base64.b64encode(png_bytes).decode()


async def get_interactive_elements(account_id: str, username: str) -> list:
    page = await get_page(account_id, username)
    elements = await page.evaluate("""() => {
        const results = [];
        const seen = new Set();
        const selectors = [
            'button', 'a[href]', 'input', 'textarea',
            '[role="button"]', '[role="link"]', '[role="tab"]',
            '[role="menuitem"]', '[role="textbox"]',
            '[data-testid]', '[tabindex="0"]'
        ];
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                if (seen.has(el)) continue;
                seen.add(el);
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                if (rect.top > window.innerHeight || rect.bottom < 0) continue;
                if (rect.left > window.innerWidth || rect.right < 0) continue;
                const text = (el.innerText || '').trim().substring(0, 80);
                const ariaLabel = el.getAttribute('aria-label') || '';
                const testId = el.getAttribute('data-testid') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || '';
                const role = el.getAttribute('role') || '';
                results.push({
                    tag, type, role, text, ariaLabel, testId, placeholder,
                    x: Math.round(rect.x + rect.width / 2),
                    y: Math.round(rect.y + rect.height / 2),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height)
                });
            }
        }
        return results;
    }""")
    numbered = []
    for i, el in enumerate(elements):
        label_parts = []
        if el.get("ariaLabel"):
            label_parts.append(el["ariaLabel"])
        if el.get("text") and el["text"] != el.get("ariaLabel", ""):
            label_parts.append(el["text"][:50])
        if el.get("testId"):
            label_parts.append(f"[{el['testId']}]")
        if el.get("placeholder"):
            label_parts.append(f"placeholder: {el['placeholder']}")
        label = " | ".join(label_parts) if label_parts else f"{el['tag']}"
        if el.get("type"):
            label = f"{el['tag']}[{el['type']}] {label}"
        numbered.append({
            "id": i,
            "label": label,
            "tag": el["tag"],
            "x": el["x"],
            "y": el["y"],
        })
    return numbered


async def click_element(account_id: str, username: str, x: int, y: int):
    page = await get_page(account_id, username)
    await page.mouse.click(x, y)
    await asyncio.sleep(0.5)


async def type_text(account_id: str, username: str, text: str):
    page = await get_page(account_id, username)
    await page.keyboard.type(text, delay=30)
    await asyncio.sleep(0.3)


async def press_key(account_id: str, username: str, key: str):
    page = await get_page(account_id, username)
    await page.keyboard.press(_translate_key(key))
    await asyncio.sleep(0.3)


async def scroll_page(account_id: str, username: str, direction: str = "down", amount: int = 3):
    page = await get_page(account_id, username)
    delta = amount * 100
    if direction == "up":
        delta = -delta
    await page.mouse.wheel(0, delta)
    await asyncio.sleep(0.5)


async def retweet_first_tweet(account_id: str, username: str) -> bool:
    page = await get_page(account_id, username)
    try:
        retweet_btn = page.locator('[data-testid="retweet"]').first
        await retweet_btn.wait_for(state="visible", timeout=10000)
        await retweet_btn.click()
        await asyncio.sleep(1)
        confirm_btn = page.locator('[data-testid="retweetConfirm"]')
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"[browser] retweet failed: {e}", flush=True)
        return False


async def like_first_tweet(account_id: str, username: str) -> bool:
    page = await get_page(account_id, username)
    try:
        like_btn = page.locator('[data-testid="like"]').first
        await like_btn.wait_for(state="visible", timeout=10000)
        await like_btn.click()
        await asyncio.sleep(1)
        return True
    except Exception as e:
        print(f"[browser] like failed: {e}", flush=True)
        return False


async def like_nth_tweet(account_id: str, username: str, n: int = 0) -> bool:
    page = await get_page(account_id, username)
    try:
        buttons = page.locator('[data-testid="like"]')
        count = await buttons.count()
        if n >= count:
            n = 0
        btn = buttons.nth(n)
        await btn.wait_for(state="visible", timeout=10000)
        await btn.click()
        await asyncio.sleep(1)
        return True
    except Exception as e:
        print(f"[browser] like_nth failed: {e}", flush=True)
        return False


async def retweet_nth_tweet(account_id: str, username: str, n: int = 0) -> bool:
    page = await get_page(account_id, username)
    try:
        buttons = page.locator('[data-testid="retweet"]')
        count = await buttons.count()
        if n >= count:
            n = 0
        btn = buttons.nth(n)
        await btn.wait_for(state="visible", timeout=10000)
        await btn.click()
        await asyncio.sleep(1)
        confirm_btn = page.locator('[data-testid="retweetConfirm"]')
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"[browser] retweet_nth failed: {e}", flush=True)
        return False


async def get_visible_tweets(account_id: str, username: str) -> list[dict]:
    page = await get_page(account_id, username)
    try:
        return await page.evaluate("""() => {
            const tweets = [];
            document.querySelectorAll('[data-testid="tweet"]').forEach(el => {
                const textEl = el.querySelector('[data-testid="tweetText"]');
                const userEl = el.querySelector('[data-testid="User-Name"] a');
                if (textEl) {
                    tweets.push({
                        text: textEl.innerText.substring(0, 280),
                        author: userEl ? userEl.getAttribute('href')?.replace('/', '') : 'unknown'
                    });
                }
            });
            return tweets.slice(0, 10);
        }""")
    except Exception as e:
        print(f"[browser] get_visible_tweets failed: {e}", flush=True)
        return []


async def follow_user(account_id: str, username: str) -> bool:
    page = await get_page(account_id, username)
    try:
        follow_btn = page.locator('[data-testid$="-follow"]').first
        await follow_btn.wait_for(state="visible", timeout=10000)
        await follow_btn.click()
        await asyncio.sleep(1)
        return True
    except Exception as e:
        print(f"[browser] follow failed: {e}", flush=True)
        return False


async def scroll_random(account_id: str, username: str):
    import random
    page = await get_page(account_id, username)
    scrolls = random.randint(1, 3)
    for _ in range(scrolls):
        delta = random.randint(300, 800)
        await page.mouse.wheel(0, delta)
        await asyncio.sleep(random.uniform(0.5, 1.5))


async def scrape_profile_stats(account_id: str, username: str) -> dict:
    page = await get_page(account_id, username)
    try:
        await page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        stats = await page.evaluate("""() => {
            const result = { followers: 0, following: 0, tweets: 0 };
            const links = document.querySelectorAll('a[href$="/followers"], a[href$="/following"], a[href$="/verified_followers"]');
            for (const a of links) {
                const text = a.innerText.replace(/,/g, '').trim();
                const match = text.match(/([\\d.]+[KMB]?)\\s/i);
                if (!match) continue;
                const num = parseCount(match[1]);
                const href = a.getAttribute('href') || '';
                if (href.includes('/followers')) result.followers = num;
                if (href.includes('/following')) result.following = num;
            }
            const header = document.querySelector('[data-testid="UserProfileHeader_Items"]');
            if (header) {
                const parent = header.closest('div[data-testid="UserName"]')?.parentElement;
            }
            // Try nav links for post count
            const navLinks = document.querySelectorAll('nav a');
            for (const a of navLinks) {
                const t = a.innerText.replace(/,/g, '').trim();
                if (/posts?$/i.test(t)) {
                    const m = t.match(/([\\d.]+[KMB]?)/i);
                    if (m) result.tweets = parseCount(m[1]);
                }
            }
            function parseCount(s) {
                s = s.toUpperCase();
                if (s.endsWith('K')) return Math.round(parseFloat(s) * 1000);
                if (s.endsWith('M')) return Math.round(parseFloat(s) * 1000000);
                if (s.endsWith('B')) return Math.round(parseFloat(s) * 1000000000);
                return parseInt(s) || 0;
            }
            return result;
        }""")
        print(f"[browser] Profile stats for @{username}: {stats}", flush=True)
        return stats
    except Exception as e:
        print(f"[browser] scrape_profile_stats failed: {e}", flush=True)
        return {"followers": 0, "following": 0, "tweets": 0}


async def scrape_following_list(
    account_id: str,
    username: str,
    target_profile: str,
    max_scroll: int = 30,
) -> list[dict]:
    page = await get_page(account_id, username)
    url = f"https://x.com/{target_profile}/following"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(3)

    all_users: dict[str, dict] = {}
    no_new_count = 0

    for _ in range(max_scroll):
        users = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('[data-testid="UserCell"]').forEach(cell => {
                const links = cell.querySelectorAll('a[href^="/"]');
                let handle = '';
                for (const a of links) {
                    const href = a.getAttribute('href') || '';
                    if (href.match(/^\\/[A-Za-z0-9_]+$/) && href !== '/') {
                        handle = href.substring(1);
                        break;
                    }
                }
                if (!handle) return;
                const nameEl = cell.querySelector('[dir="ltr"] > span');
                const bioEl = cell.querySelector('[style*="color"] > span');
                results.push({
                    username: handle,
                    display_name: nameEl ? nameEl.innerText.trim() : '',
                    bio: bioEl ? bioEl.innerText.trim().substring(0, 300) : ''
                });
            });
            return results;
        }""")

        prev_count = len(all_users)
        for u in users:
            if u["username"] not in all_users:
                all_users[u["username"]] = u

        if len(all_users) == prev_count:
            no_new_count += 1
            if no_new_count >= 2:
                break
        else:
            no_new_count = 0

        await page.mouse.wheel(0, 600)
        await asyncio.sleep(1.5)

    print(
        f"[browser] Scraped {len(all_users)} users from @{target_profile}/following",
        flush=True,
    )
    return list(all_users.values())


async def type_in_reply_box(account_id: str, username: str, text: str) -> bool:
    page = await get_page(account_id, username)
    try:
        reply_box = page.locator('[data-testid="tweetTextarea_0"]').first
        await reply_box.wait_for(state="visible", timeout=10000)
        await reply_box.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type(text, delay=30)
        await asyncio.sleep(0.5)
        post_btn = page.locator('[data-testid="tweetButtonInline"]')
        await post_btn.wait_for(state="visible", timeout=5000)
        await post_btn.click()
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"[browser] type_in_reply_box failed: {e}", flush=True)
        return False


async def execute_action(account_id: str, username: str, action: dict):
    page = await get_page(account_id, username)
    action_type = action.get("action")

    if action_type == "screenshot":
        return

    elif action_type == "left_click":
        x, y = action["coordinate"]
        await page.mouse.click(x, y)

    elif action_type == "right_click":
        x, y = action["coordinate"]
        await page.mouse.click(x, y, button="right")

    elif action_type == "double_click":
        x, y = action["coordinate"]
        await page.mouse.dblclick(x, y)

    elif action_type == "middle_click":
        x, y = action["coordinate"]
        await page.mouse.click(x, y, button="middle")

    elif action_type == "mouse_move":
        x, y = action["coordinate"]
        await page.mouse.move(x, y)

    elif action_type == "type":
        text = action.get("text", "")
        await page.keyboard.type(text, delay=30)

    elif action_type == "key":
        key = action.get("text", "")
        key = _translate_key(key)
        await page.keyboard.press(key)

    elif action_type == "scroll":
        x, y = action.get("coordinate", [640, 400])
        direction = action.get("scroll_direction", "down")
        amount = action.get("scroll_amount", 3)
        delta = amount * 100
        if direction == "up":
            delta = -delta
        elif direction == "left":
            await page.mouse.move(x, y)
            await page.evaluate(f"window.scrollBy(-{delta}, 0)")
            return
        elif direction == "right":
            await page.mouse.move(x, y)
            await page.evaluate(f"window.scrollBy({delta}, 0)")
            return
        await page.mouse.move(x, y)
        await page.mouse.wheel(0, delta)

    await asyncio.sleep(0.5)


def _translate_key(key_str: str) -> str:
    mapping = {
        "return": "Enter",
        "enter": "Enter",
        "tab": "Tab",
        "escape": "Escape",
        "backspace": "Backspace",
        "delete": "Delete",
        "space": " ",
        "up": "ArrowUp",
        "down": "ArrowDown",
        "left": "ArrowLeft",
        "right": "ArrowRight",
    }
    parts = key_str.lower().split("+")
    translated = []
    for p in parts:
        p = p.strip()
        translated.append(mapping.get(p, p.capitalize() if len(p) == 1 else p))
    return "+".join(translated)


async def save_session(account_id: str, username: str):
    if account_id in _contexts:
        context = _contexts[account_id]
        context_dir = BROWSERS_DIR / username
        context_dir.mkdir(parents=True, exist_ok=True)
        state = await context.storage_state()
        import json
        (context_dir / "state.json").write_text(json.dumps(state))


async def open_login_browser(account_id: str, username: str) -> tuple[str, BrowserContext]:
    browser = await _ensure_browser()
    context_dir = BROWSERS_DIR / username
    context_dir.mkdir(parents=True, exist_ok=True)

    context = await browser.new_context(
        viewport={"width": settings.display_width, "height": settings.display_height},
        locale="en-US",
        timezone_id="America/New_York",
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)
    _contexts[account_id] = context
    page = await context.new_page()
    _pages[account_id] = page
    await page.goto("https://x.com/login", wait_until="domcontentloaded")
    return str(context_dir), context


async def close_context(account_id: str):
    if account_id in _pages:
        page = _pages.pop(account_id)
        if not page.is_closed():
            await page.close()
    if account_id in _contexts:
        context = _contexts.pop(account_id)
        await context.close()


async def shutdown():
    global _browser, _playwright
    for aid in list(_contexts.keys()):
        await close_context(aid)
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
