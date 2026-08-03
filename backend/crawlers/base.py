# intel-monitor/backend/crawlers/base.py
import asyncio
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class CommentData:
    text: str
    author: str
    likes: int = 0
    url: str = ""
    reply_count: int = 0      # 评论底下的回复数（微博 hotflow）
    retweet_count: int = 0    # 评论被转发数（X thread）


@dataclass
class PostData:
    url: str
    title: str = ""
    content: str = ""
    likes: int = 0
    comments_count: int = 0
    shares: int = 0
    views: int = 0
    bookmarks: int = 0
    author_name: str = ""
    author_avatar: str = ""
    author_followers: int = 0
    published_at: datetime | None = None
    comments: list[CommentData] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    videos: list[dict] = field(default_factory=list)
    quoted_tweet: dict | None = None
    card: dict | None = None


@dataclass
class CrawlResult:
    posts: list[PostData] = field(default_factory=list)
    raw_html: str = ""
    success: bool = True
    error_message: str = ""



class PlaywrightCrawler(ABC):
    """Base for Playwright-based platform crawlers. Not for OpenCLI/CDP/Claude."""

    def __init__(self):
        self.browser = None
        self.page = None
        self._playwright = None

    async def init_browser(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    @abstractmethod
    async def crawl(self, account_url: str) -> CrawlResult:
        pass

    @abstractmethod
    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        pass


async def _run_crawler_in_thread(coro):
    """Run a Playwright crawler coroutine in a thread with ProactorEventLoop on Windows."""
    if sys.platform == "win32":
        import concurrent.futures

        def _run_in_proactor():
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await asyncio.get_event_loop().run_in_executor(pool, _run_in_proactor)
    return await coro


# ── Time parsing utilities ─────────────────────────────────────────────────

_RELATIVE_EN = re.compile(
    r'(\d+)\s*(minute|hour|day|week|month|year)s?\s*ago', re.IGNORECASE
)
_RELATIVE_ZH = re.compile(
    r'(\d+)\s*个?\s*(分钟|小时|天|周|月|年)前'
)

_UNIT_MAP = {
    'minute': 'minutes', 'minutes': 'minutes',
    'hour': 'hours', 'hours': 'hours',
    'day': 'days', 'days': 'days',
    'week': 'weeks', 'weeks': 'weeks',
    'month': 'months', 'months': 'months',
    'year': 'years', 'years': 'years',
    '分钟': 'minutes', '小时': 'hours', '天': 'days',
    '周': 'weeks', '月': 'months', '年': 'years',
}

TZ_SHANGHAI = timezone(timedelta(hours=8))
TZ_UTC = timezone.utc


def parse_relative_time(text: str, now: datetime | None = None) -> datetime | None:
    """Parse relative time strings (Chinese and English) into naive UTC datetime.

    Handles: "3 days ago", "2小时前", "5分钟前", "1 week ago", "3个月前", etc.
    Returns naive UTC datetime (tzinfo=None) for SQLite storage compatibility.
    """
    if not text or not text.strip():
        return None
    if now is None:
        now = datetime.now(TZ_UTC)

    m = _RELATIVE_ZH.search(text) or _RELATIVE_EN.search(text)
    if not m:
        return None

    amount = int(m.group(1))
    unit_key = _UNIT_MAP.get(m.group(2))
    if not unit_key:
        return None

    result = now - timedelta(**{unit_key: amount}) if unit_key not in ('months', 'years') else (
        now - timedelta(days=amount * 30) if unit_key == 'months' else now - timedelta(days=amount * 365)
    )
    return result.replace(tzinfo=None)  # naive UTC


def parse_absolute_time(text: str, assume_utc: bool = False) -> datetime | None:
    """Parse absolute datetime strings into naive UTC datetime.

    Tries common formats found across platforms.
    assume_utc=True  → naive datetime treated as UTC.
    assume_utc=False → naive datetime treated as Asia/Shanghai (default, for Chinese platforms).
    Returns naive UTC datetime (tzinfo=None) for SQLite storage compatibility.
    """
    if not text or not text.strip():
        return None

    text = text.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            if fmt == "%m-%d":
                dt = dt.replace(year=datetime.now().year)
            if assume_utc:
                return dt.replace(tzinfo=TZ_UTC)
            return dt.replace(tzinfo=TZ_SHANGHAI).astimezone(TZ_UTC).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def filter_posts(posts: list, post_limit: int = 10, time_range_days: int = 0) -> list:
    """Filter posts by time range and limit count.

    Posts without published_at are excluded when time filtering is active.
    All published_at values are expected to be naive UTC datetimes.
    """
    filtered = posts

    if time_range_days > 0:
        cutoff = datetime.now(TZ_UTC).replace(tzinfo=None) - timedelta(days=time_range_days)
        filtered = [
            p for p in filtered
            if p.published_at is not None and p.published_at >= cutoff
        ]

    return filtered[:post_limit]
