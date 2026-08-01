# intel-monitor/backend/crawlers/telegram/bot.py
"""
Telegram Web Bot driver using Playwright persistent context.

Key flows:
  - start()  – launch browser, detect login state
  - send_message(text) – type + send in the current chat
  - wait_for_bot_reply(timeout) – wait for result links to appear
  - click_result_and_extract() – click a result → extract body → return to @kuai
"""
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx

from crawlers.base import PostData
from crawlers.telegram.parser import (
    parse_channel_message, parse_subscriber_count, parse_message_timestamp,
    is_ad_result,
)

logger = logging.getLogger(__name__)

TELEGRAM_WEB_URL = "https://web.telegram.org/k/"
KUAI_CHAT_URL = "https://web.telegram.org/k/#@kuai"
DEFAULT_PROFILE_DIRS: list[str] = [
    str(Path(__file__).resolve().parents[3] / "data" / "telegram_profile"),
    str(Path(__file__).resolve().parents[2] / "data" / "telegram_profile"),
]


def _resolve_profile_dir(override: str | None = None) -> str:
    """Return the first existing profile dir, or the primary default."""
    if override:
        return override
    env = os.environ.get("TELEGRAM_PROFILE_DIR")
    if env:
        return env
    for d in DEFAULT_PROFILE_DIRS:
        if Path(d).exists():
            return d
    return DEFAULT_PROFILE_DIRS[0]

# Per-message delay to avoid Flood Wait
MESSAGE_INTERVAL_S = 1.5

# Bot reply wait timeout
BOT_REPLY_TIMEOUT_S = 20


class TelegramLoginRequired(RuntimeError):
    """Raised when Telegram Web is not logged in (QR code page shown)."""


class TelegramBot:
    """Encapsulates a Playwright persistent context for Telegram Web K."""

    def __init__(self, profile_dir: str | None = None):
        self._profile_dir = _resolve_profile_dir(profile_dir)
        self._playwright = None
        self._context = None
        self._page = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self):
        """Connect to user's Chrome via CDP, reusing existing Telegram Web login session."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Discover Chrome CDP port
        cdp_url = await self._discover_cdp_endpoint()
        if not cdp_url:
            # Fallback: persistent context (legacy path, requires init_telegram.py)
            logger.warning("CDP not available, falling back to headless persistent context")
            Path(self._profile_dir).mkdir(parents=True, exist_ok=True)
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir,
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
                viewport={"width": 1280, "height": 900},
            )
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        else:
            logger.info("Connecting to Chrome CDP: %s", cdp_url)
            browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
            # Reuse the default context (preserves user's login cookies)
            contexts = browser.contexts
            if contexts:
                self._context = contexts[0]
            else:
                self._context = await browser.new_context(
                    viewport={"width": 1280, "height": 900},
                )

            # Find or create a page in this context
            pages = self._context.pages
            if pages:
                self._page = pages[0]
            else:
                self._page = await self._context.new_page()

        await self._page.goto(TELEGRAM_WEB_URL, wait_until="domcontentloaded", timeout=30000)
        # Telegram Web K is a heavy SPA; wait for it to hydrate
        await self._wait_for_spa_ready()

        if not await self._is_logged_in():
            raise TelegramLoginRequired(
                "Telegram 未登录。请在 Chrome 中打开 web.telegram.org/k/ 扫码登录后重试。"
            )

        logger.info("TelegramBot started via CDP, logged in")

    async def close(self):
        """Disconnect from browser. Does NOT close Chrome tabs/contexts."""
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._playwright = None

    # ── Login detection ───────────────────────────────────────────────────

    async def _discover_cdp_endpoint(self) -> str | None:
        """Discover the Chrome DevTools debugging endpoint.

        Checks, in order:
        1.  ``DevToolsActivePort`` files from Chromium-family user-data dirs
            (chrome://inspect#remote-debugging toggle).  These contain the
            actual port on the first line and an optional wsPath on line 2.
        2.  Fallback: scan fixed ports 9222 … 9226.

        Returns an ``http://localhost:<port>`` URL suitable for
        :meth:`chromium.connect_over_cdp`, or *None*.
        """
        import os as _os

        # ── 1. Read DevToolsActivePort ──────────────────────────────
        home = str(Path.home())
        candidates: list[Path] = []
        local_app_data = _os.environ.get("LOCALAPPDATA", "")
        if local_app_data:  # Windows
            candidates = [
                Path(local_app_data) / "Google" / "Chrome" / "User Data" / "DevToolsActivePort",
                Path(local_app_data) / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort",
                Path(local_app_data) / "Chromium" / "User Data" / "DevToolsActivePort",
            ]
        elif _os.name == "posix" and "darwin" in _os.uname().sysname.lower():
            candidates = [
                Path(home) / "Library/Application Support/Google/Chrome/DevToolsActivePort",
                Path(home) / "Library/Application Support/Microsoft Edge/DevToolsActivePort",
            ]
        else:  # Linux
            candidates = [
                Path(home) / ".config/google-chrome/DevToolsActivePort",
                Path(home) / ".config/microsoft-edge/DevToolsActivePort",
            ]

        for fp in candidates:
            try:
                lines = fp.read_text(encoding="utf-8").strip().splitlines()
                port = int(lines[0])
                if 0 < port < 65536:
                    url = f"http://localhost:{port}"
                    # Quick health check
                    async with httpx.AsyncClient(timeout=1.5) as client:
                        resp = await client.get(f"{url}/json/version")
                        if resp.status_code == 200:
                            logger.debug("CDP found via %s → port %d", fp, port)
                            return url
            except Exception:
                continue

        # ── 2. Fixed-port scan ─────────────────────────────────────
        for port in (9222, 9223, 9224, 9225, 9226):
            try:
                async with httpx.AsyncClient(timeout=1.5) as client:
                    resp = await client.get(f"http://localhost:{port}/json/version")
                    if resp.status_code == 200:
                        logger.debug("CDP found on fixed port %d", port)
                        return f"http://localhost:{port}"
            except Exception:
                continue
        return None

    async def _wait_for_spa_ready(self):
        """Wait for Telegram Web K SPA to finish hydrating.

        The page loads in ~1 s but the React app takes several more seconds
        to render meaningful content.  We poll until buttons or inputs appear.
        """
        deadline = datetime.utcnow().timestamp() + 15
        while datetime.utcnow().timestamp() < deadline:
            try:
                # Once the React app mounts, either a QR login button or the
                # chat UI (inputs, buttons) will be present.
                btn_count = await self._page.locator("button").count()
                input_count = await self._page.locator("input").count()
                if btn_count > 0 or input_count > 0:
                    return
            except Exception:
                pass
            await asyncio.sleep(1)

    async def _is_logged_in(self) -> bool:
        """Return True if the current page shows the main Telegram UI (not QR login)."""
        try:
            # QR code page has "Log in by QR Code" heading
            content = await self._page.text_content("body") or ""
            if "Log in to Telegram by QR Code" in content:
                return False
            if "Log in by QR Code" in content:
                return False
            # If we see a search textbox with placeholder "Search", we're logged in
            search_el = self._page.locator('input[placeholder*="Search"]')
            if await search_el.count() > 0:
                return True
            # Fallback: check for common logged-in signals
            if "" in content or "Saved Messages" in content:
                return True
            return False
        except Exception:
            return False

    # ── Navigation ────────────────────────────────────────────────────────

    async def _navigate_to_kuai(self):
        """Ensure we are on the @kuai chat page."""
        current = self._page.url
        if current == KUAI_CHAT_URL or current.rstrip("/") == KUAI_CHAT_URL:
            return
        await self._page.goto(KUAI_CHAT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

    async def _return_to_kuai(self):
        """Navigate back to @kuai chat (full reload, not back())."""
        await self._page.goto(KUAI_CHAT_URL, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1.5)

    # ── Sending messages ──────────────────────────────────────────────────

    async def send_message(self, text: str):
        """Send a text message in the currently open chat."""
        # Click the message input area (div[contenteditable="true"] inside the bottom bar)
        input_sel = 'div[contenteditable="true"]'
        await self._page.wait_for_selector(input_sel, timeout=10000)
        await self._page.click(input_sel)
        await asyncio.sleep(0.3)

        # Clear any existing text by selecting all then typing
        await self._page.keyboard.press("Control+A")
        await self._page.keyboard.type(text, delay=50)
        await asyncio.sleep(0.3)

        # Press Enter to send
        await self._page.keyboard.press("Enter")
        logger.info("Sent message to @kuai: %s", text[:80])

    # ── Waiting for Bot reply ─────────────────────────────────────────────

    async def wait_for_bot_reply(self, timeout_s: int = BOT_REPLY_TIMEOUT_S) -> list[dict]:
        """Wait for @kuai Bot to reply with search results, then parse them.

        Returns a list of dicts with keys:
          title, url, icon_type (image/video/document/unknown), is_ad
        """
        deadline = datetime.utcnow().timestamp() + timeout_s

        # Wait until we see result-style links in the latest Bot reply bubble
        # Bot reply bubbles contain t.me/ links
        while datetime.utcnow().timestamp() < deadline:
            try:
                items = await self._extract_result_items_from_page()
                # Bot results always contain links — we need at least 1 non-ad link
                real_items = [it for it in items if not it.get("is_ad")]
                if real_items:
                    logger.info("Bot reply received: %d items (%d non-ad)", len(items), len(real_items))
                    return items
            except Exception as e:
                logger.debug("wait_for_bot_reply polling error: %s", e)
            await asyncio.sleep(1.5)

        logger.warning("Bot reply timed out after %ds", timeout_s)
        return []

    async def _extract_result_items_from_page(self) -> list[dict]:
        """Extract result items from the current @kuai chat page DOM.

        Bot reply structure:
          - Each result is a clickable <a> link containing icon emoji + title text
          - Ad results are prefixed with '广告'
          - Content-type icons: 🏞 image, 🎬 video, 📄 document
        """
        items = []

        # Select all link elements inside message bubbles
        # Telegram Web K uses <a> tags with href to t.me or tg: scheme
        links = await self._page.locator('a[href*="t.me/"]').all()

        seen_urls = set()
        for link_el in links:
            try:
                href = await link_el.get_attribute("href") or ""
                if not href or "t.me/" not in href:
                    continue
                # Normalize URL
                if href.startswith("tg://"):
                    # Could be tg://resolve style, skip for now
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                text = (await link_el.inner_text()).strip()

                # Determine content type from icon prefix
                icon_type = "unknown"
                for icon, ctype in {"\U0001f3de": "image", "\U0001f3ac": "video", "\U0001f4c4": "document"}.items():
                    if icon in text:
                        icon_type = ctype
                        break

                # Detect ads
                is_ad = "广告" in text[:10]

                items.append({
                    "title": text,
                    "url": href,
                    "icon_type": icon_type,
                    "is_ad": is_ad,
                })
            except Exception:
                continue

        return items

    # ── Click result → extract body → return ──────────────────────────────

    async def click_result_and_extract(self, result_url: str) -> PostData | None:
        """Click a result link to navigate to the channel message,
        extract full body, then return to @kuai.

        Args:
            result_url: Full t.me URL like https://t.me/gy0hxsoqt4xd/13214

        Returns:
            PostData with parsed title, content, images, author, and timestamp,
            or None if extraction failed entirely.
        """
        try:
            # Navigate to the channel message
            await self._page.goto(result_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(2)  # Let message content render

            # Extract channel name / subscriber count from header
            author_name = ""
            author_followers = 0
            try:
                # Channel header appears as a link or text above messages
                header_el = self._page.locator('.chat-info, .peer-title, [class*="title"]').first
                if await header_el.count() > 0:
                    header_text = await header_el.inner_text()
                    if header_text:
                        author_name = header_text.strip()
            except Exception:
                pass

            # Subscriber count
            try:
                body_text = await self._page.inner_text("body") or ""
                for line in body_text.split("\n"):
                    if "subscribers" in line.lower() or "subscriber" in line.lower():
                        author_followers = parse_subscriber_count(line)
                        break
            except Exception:
                pass

            # Extract the main message content
            page_text = await self._page.inner_text("body") or ""

            # Try to get message-specific content (inside the bubbles container)
            try:
                bubbles = self._page.locator('.bubbles, .messages-container, [class*="messages"]')
                if await bubbles.count() > 0:
                    page_text = await bubbles.first.inner_text()
            except Exception:
                pass

            post = parse_channel_message(page_text, result_url)
            if author_name:
                post.author_name = author_name
            if author_followers:
                post.author_followers = author_followers

            # Try to extract timestamp from the message header
            try:
                time_els = self._page.locator('.time, [class*="time"], .message-time, [class*="date"]')
                if await time_els.count() > 0:
                    time_text = await time_els.first.inner_text()
                    ts = parse_message_timestamp(time_text)
                    if ts:
                        post.published_at = ts
            except Exception:
                pass

            # Extract images if present
            try:
                img_els = self._page.locator('.bubble img.media-photo, .photo img, img.media-photo, img[src*="file"]')
                count = await img_els.count()
                for i in range(min(count, 5)):
                    src = await img_els.nth(i).get_attribute("src") or ""
                    if src and (src.startswith("http") or src.startswith("blob:") or src.startswith("/")):
                        if src.startswith("/"):
                            src = "https://web.telegram.org" + src
                        post.images.append(src)
            except Exception:
                pass

            # Extract comment/view counts if visible
            try:
                footer_text = await self._page.inner_text("body") or ""
                import re
                # Telegram shows "N comments" or "N replies" sometimes
                cm = re.search(r'(\d+)\s*(comment|reply|comments|replies)', footer_text, re.IGNORECASE)
                if cm:
                    post.comments_count = int(cm.group(1))
                # "N views" is rare in Telegram but sometimes present
                vm = re.search(r'(\d[\d,.]*)\s*views?', footer_text, re.IGNORECASE)
                if vm:
                    post.views = int(vm.group(1).replace(",", "").replace(".", ""))
            except Exception:
                pass

            logger.info(
                "Extracted channel message: title=%s, author=%s, images=%d",
                post.title[:60], post.author_name, len(post.images),
            )

            # Return to @kuai
            await self._return_to_kuai()

            return post

        except Exception as e:
            logger.warning("Failed to extract message from %s: %s", result_url, e)
            # Try to return to @kuai even on failure
            try:
                await self._return_to_kuai()
            except Exception:
                pass
            return None
