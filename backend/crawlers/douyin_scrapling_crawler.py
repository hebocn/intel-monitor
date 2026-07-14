"""
Douyin crawler via Scrapling StealthyFetcher + adaptive CSS selectors.
Prototype — eliminates the need for user Chrome CDP (localhost:9222).

Key advantages over current douyin_crawler.py:
  1. No Chrome CDP dependency — StealthyFetcher launches its own stealth browser
  2. Adaptive selectors (auto_save + adaptive) survive DOM changes
  3. Built-in Cloudflare bypass (solve_cloudflare=True)
  4. Built-in fingerprint spoofing (hide_canvas, browserforge headers)
"""
import logging
import asyncio
from crawlers.base import CrawlResult, PostData, parse_relative_time, parse_absolute_time

logger = logging.getLogger(__name__)

# ── Session IDs static so they can be configured ──────────────────────────
SAVE_ID = "douyin_posts"
SEARCH_SAVE_ID = "douyin_search"


class DouyinScraplingCrawler:
    """Douyin crawler using Scrapling's stealth browser with adaptive selectors."""

    async def crawl(self, account_url: str) -> CrawlResult:
        """Fetch posts from a Douyin user page."""
        return await asyncio.to_thread(self._do_crawl, account_url)

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        """Search Douyin for keyword. Requires session to avoid re-auth."""
        from urllib.parse import quote
        search_url = f"https://www.douyin.com/search/{quote(keyword)}"
        return await asyncio.to_thread(self._do_search, search_url, limit)

    # ── Thread-mode helpers ──────────────────────────────────────────────

    @staticmethod
    def _is_blocked(text: str) -> bool:
        """Detect Douyin anti-bot blocks in page content."""
        signals = [
            "验证码", "captcha", "滑块验证", "请完成安全验证",
            "请先登录", "请登录", "需要登录",
        ]
        check = text[:500].lower()
        return any(s in check for s in signals)

    @staticmethod
    def _extract_time(el) -> str:
        """Try multiple selectors to find a time string on a post element."""
        for sel in ['span[class*="time"]', '.time', '.date', 'span:last-child']:
            time_els = el.css(sel)
            if time_els and time_els[0].text and time_els[0].text.strip():
                return time_els[0].text.strip()
        return ""

    def _extract_posts(self, response, limit: int = 10) -> CrawlResult:
        """Parse Douyin posts from response using adaptive selectors.

        Uses auto_save to store element fingerprints.
        On subsequent runs, use adaptive=True to relocate after DOM changes.
        """
        # Try adaptive-enabled selectors; auto_save stores fingerprints for future use
        post_selectors = [
            'li[class*="item"]',
            'div[class*="video-card"]',
            'a[href*="/video/"]',
        ]
        posts_raw = []
        for sel in post_selectors:
            posts_raw = response.css(sel, auto_save=True)
            if posts_raw:
                logger.info(f"DouyinScrapling: matched {len(posts_raw)} elements with '{sel}'")
                break

        if not posts_raw:
            return CrawlResult(
                success=False,
                error_message="未找到帖子元素，页面结构可能已变化或需要登录"
            )

        posts = []
        for el in posts_raw[:limit]:
            try:
                # Title extraction
                title = ""
                for s in ['p', '.title', 'span[class*="title"]']:
                    title_els = el.css(s)
                    if title_els and title_els[0].text and title_els[0].text.strip():
                        title = title_els[0].text.strip()
                        break

                # URL extraction
                href = ""
                try:
                    href = el.attrib.get('href', '') if hasattr(el, 'attrib') else ''
                except Exception:
                    pass
                url = f"https://www.douyin.com{href}" if href.startswith("/") else href

                # Time extraction
                time_text = self._extract_time(el)
                published_at = parse_relative_time(time_text) or parse_absolute_time(time_text)

                if title:
                    posts.append(PostData(
                        url=url, title=title,
                        published_at=published_at,
                    ))

            except Exception as e:
                logger.debug(f"DouyinScrapling parse error: {e}")
                continue

        return CrawlResult(posts=posts, success=len(posts) > 0)

    # ── Core fetch logic ──────────────────────────────────────────────────

    def _do_crawl(self, account_url: str) -> CrawlResult:
        from scrapling import StealthyFetcher

        try:
            logger.info(f"DouyinScrapling: fetching {account_url}")
            response = StealthyFetcher.fetch(
                url=account_url,
                headless=True,
                network_idle=True,
                wait=5000,
                solve_cloudflare=True,
                disable_resources=True,
                block_ads=True,
                timeout=60000,
                locale="zh-CN",
            )

            if self._is_blocked(response.text):
                return CrawlResult(
                    success=False,
                    error_message="被抖音反爬拦截（验证码/登录墙）"
                )

            return self._extract_posts(response)

        except Exception as e:
            logger.exception("DouyinScrapling crawl error")
            return CrawlResult(success=False, error_message=f"Scrapling 抓取失败: {e}")

    def _do_search(self, search_url: str, limit: int) -> CrawlResult:
        from scrapling import StealthyFetcher

        try:
            # Step 1: Visit homepage to establish a browser session identity
            logger.info("DouyinScrapling: warming up (visiting homepage)")
            StealthyFetcher.fetch(
                url="https://www.douyin.com/",
                headless=True,
                wait=5000,
                solve_cloudflare=True,
                timeout=45000,
                locale="zh-CN",
            )

            # Step 2: Navigate to search page
            logger.info(f"DouyinScrapling: searching {search_url}")
            response = StealthyFetcher.fetch(
                url=search_url,
                headless=True,
                network_idle=True,
                wait=10000,  # SPA needs more time for JS rendering
                solve_cloudflare=True,
                disable_resources=True,
                block_ads=True,
                timeout=90000,
                locale="zh-CN",
            )

            if self._is_blocked(response.text):
                return CrawlResult(
                    success=False,
                    error_message="搜索被抖音反爬拦截（验证码/登录墙）"
                )

            return self._extract_posts(response, limit)

        except Exception as e:
            logger.exception("DouyinScrapling search error")
            return CrawlResult(success=False, error_message=f"Scrapling 搜索失败: {e}")
