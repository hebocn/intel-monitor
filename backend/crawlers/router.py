"""
Crawler router — unified fallback chain.

Each CrawlerEntry wraps one crawler method (OpenCLI, CDP, Playwright, Claude).
The router tries them in priority order and returns the first successful result.
"""
import logging
from dataclasses import dataclass
from collections.abc import Callable, Coroutine
from typing import Any

from crawlers.base import CrawlResult

logger = logging.getLogger(__name__)


@dataclass
class CrawlerEntry:
    name: str
    platforms: frozenset[str]
    crawl: Callable[..., Coroutine[Any, Any, CrawlResult]]
    available: Callable[[], Coroutine[Any, Any, bool]]


class CrawlerRouter:
    def __init__(self, entries: list[CrawlerEntry] | None = None):
        self.entries: list[CrawlerEntry] = entries or []

    def register(self, entry: CrawlerEntry):
        self.entries.append(entry)

    async def crawl(
        self, platform: str, account_name: str, account_url: str, post_limit: int = 10
    ) -> tuple[CrawlResult | None, str, list[str]]:
        """Try each entry in priority order. Returns (result, method_name, error_log)."""
        error_log: list[str] = []

        for entry in self.entries:
            if platform not in entry.platforms:
                continue

            try:
                if not await entry.available():
                    error_log.append(f"{entry.name}: not available")
                    continue
            except Exception as e:
                error_log.append(f"{entry.name}: availability check failed ({e})")
                continue

            logger.info(f"[{account_name}] trying {entry.name} (platform={platform})")
            try:
                result = await entry.crawl(platform, account_name, account_url, post_limit)
                if result.success:
                    logger.info(f"[{account_name}] {entry.name} success: {len(result.posts)} posts")
                    return result, entry.name, error_log
                error_log.append(f"{entry.name}: {result.error_message}")
                logger.warning(f"[{account_name}] {entry.name} failed: {result.error_message}")
            except Exception as e:
                error_log.append(f"{entry.name}: {e}")
                logger.warning(f"[{account_name}] {entry.name} exception: {e}")

        return None, "none", error_log

    def platform_methods(self, platform: str) -> list[str]:
        return [e.name for e in self.entries if platform in e.platforms]
