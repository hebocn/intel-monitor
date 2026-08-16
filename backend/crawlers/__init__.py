from crawlers.base import (
    PlaywrightCrawler, CrawlResult, PostData, CommentData,
    filter_posts, _run_crawler_in_thread,
    parse_relative_time, parse_absolute_time,
)
from crawlers.router import CrawlerEntry, CrawlerRouter
from crawlers.website_crawler import WebsiteCrawler
from crawlers.x_crawler import XCrawler
from crawlers.youtube_crawler import YouTubeCrawler
from crawlers.xiaohongshu_crawler import XiaoHongShuCrawler
from crawlers.douyin_crawler import DouyinCrawler
from crawlers.weibo_crawler import WeiboCrawler
from crawlers.toutiao_crawler import ToutiaoCrawler
from crawlers.tiantai108_crawler import Tiantai108Crawler
from crawlers.opencli_crawler import OpenCLICrawler, build_opencli_entry
from crawlers.cdp_crawler import build_cdp_entry
from crawlers.claude_crawler import build_claude_entry
from crawlers.toutiao_scrapling_crawler import ToutiaoScraplingCrawler
from crawlers.douyin_scrapling_crawler import DouyinScraplingCrawler
from crawlers.facebook_crawler import FacebookCrawler

CRAWLER_MAP = {
    "x": XCrawler,
    "youtube": YouTubeCrawler,
    "xiaohongshu": XiaoHongShuCrawler,
    "douyin": DouyinCrawler,
    "weibo": WeiboCrawler,
    "toutiao": ToutiaoCrawler,
    "108community": Tiantai108Crawler,
    "facebook": FacebookCrawler,
}

_router: CrawlerRouter | None = None


def _build_playwright_entry() -> CrawlerEntry:
    async def _check():
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def _crawl(platform, account_name, account_url, post_limit=10):
        crawler_cls = CRAWLER_MAP.get(platform)
        if not crawler_cls:
            return CrawlResult(success=False, error_message=f"Playwright: unsupported platform {platform}")
        crawler = crawler_cls()
        return await _run_crawler_in_thread(crawler.crawl(account_url))

    return CrawlerEntry(
        name="playwright",
        platforms=frozenset(CRAWLER_MAP.keys()),
        crawl=_crawl,
        available=_check,
    )


def _build_scrapling_entry() -> CrawlerEntry:
    """Scrapling stealth browser entry — for platforms where no login is required.
    Tried before Playwright CDP connection (no user Chrome needed)."""
    async def _check():
        try:
            from scrapling import StealthyFetcher  # noqa: F401
            return True
        except ImportError:
            return False

    async def _crawl(platform, account_name, account_url, post_limit=10):
        if platform == "toutiao":
            crawler = ToutiaoScraplingCrawler()
            return await crawler.crawl(account_url)
        # Future: douyin (if login not needed), 108community, etc.
        return CrawlResult(success=False, error_message=f"Scrapling: unsupported platform {platform}")

    return CrawlerEntry(
        name="scrapling",
        platforms=frozenset({"toutiao"}),  # expand as more platforms prove viable
        crawl=_crawl,
        available=_check,
    )


def build_default_router() -> CrawlerRouter:
    return CrawlerRouter([
        build_opencli_entry(),
        build_cdp_entry(),
        _build_scrapling_entry(),
        _build_playwright_entry(),
        # Claude entry not registered by default — enable explicitly if needed:
        # build_claude_entry(),
    ])


def get_router() -> CrawlerRouter:
    global _router
    if _router is None:
        _router = build_default_router()
    return _router


__all__ = [
    "PlaywrightCrawler", "CrawlResult", "PostData", "CommentData",
    "CrawlerEntry", "CrawlerRouter",
    "get_router", "build_default_router",
    "filter_posts", "_run_crawler_in_thread",
    "XCrawler", "YouTubeCrawler", "XiaoHongShuCrawler", "DouyinCrawler",
    "WeiboCrawler", "ToutiaoCrawler", "Tiantai108Crawler",
    "FacebookCrawler",
    "WebsiteCrawler", "OpenCLICrawler",
    "ToutiaoScraplingCrawler", "DouyinScraplingCrawler",
    "CRAWLER_MAP",
]
