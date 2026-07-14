# intel-monitor/backend/crawlers/toutiao_crawler.py
import os
import logging
from urllib.parse import quote
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData, parse_relative_time, parse_absolute_time

logger = logging.getLogger(__name__)

CDP_URL = os.getenv("CHROME_CDP_URL", "http://localhost:9222")


class ToutiaoCrawler(PlaywrightCrawler):
    """Toutiao crawler using CDP to reuse user's logged-in Chrome."""

    async def init_browser(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        try:
            self.browser = await self._playwright.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            raise RuntimeError(
                f"Cannot connect to Chrome at {CDP_URL}. "
                f"Start Chrome with: chrome --remote-debugging-port=9222. Error: {e}"
            )
        # Use existing browser context to keep login session
        contexts = self.browser.contexts
        if contexts:
            self.page = await contexts[0].new_page()
        else:
            self.page = await self.browser.new_page()

    async def close(self):
        if self.page:
            await self.page.close()
            self.page = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)
            return await self._parse_search_results(20)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        try:
            await self.init_browser()
            encoded_kw = quote(keyword)
            search_url = f"https://so.toutiao.com/search?keyword={encoded_kw}"
            await self.page.goto(search_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(4000)

            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 800)")
                await self.page.wait_for_timeout(1500)

            return await self._parse_search_results(limit)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def _parse_search_results(self, limit: int) -> CrawlResult:
        posts = []

        result_selectors = [
            '.search-result-item', '.result-item', 'div[class*="result"]',
            '.article-item', 'div[class*="article"]', 'a[href*="/a"]',
        ]

        for sel in result_selectors:
            elements = await self.page.query_selector_all(sel)
            if elements:
                break

        for el in elements[:limit]:
            try:
                title_el = await el.query_selector(
                    'a[class*="title"], .title, h3, h2, a[href*="/group/"], span[class*="title"]'
                )
                title = await title_el.inner_text() if title_el else ""

                href = ""
                try:
                    href = await title_el.get_attribute("href") if title_el else ""
                except Exception:
                    href = await el.get_attribute("href") or ""

                url = f"https://so.toutiao.com{href}" if href.startswith("/") else href

                comments = await self._extract_metric(el, ['[class*="comment"]', '.comment-count', 'span:last-child'])
                author = await self._extract_text(el, ['[class*="source"]', '.author', '.source', 'span[class*="name"]'])

                time_text = await self._extract_text(el, ['span[class*="time"]', '.time', '.date'])
                published_at = parse_relative_time(time_text) or parse_absolute_time(time_text)

                if title and title.strip():
                    posts.append(PostData(
                        url=url, title=title.strip(), content=title.strip(),
                        comments_count=comments, author_name=author,
                        published_at=published_at,
                    ))
            except Exception:
                continue

        return CrawlResult(posts=posts, success=len(posts) > 0)

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        return []

    async def _extract_metric(self, el, selectors: list[str]) -> int:
        for sel in selectors:
            try:
                metric_el = await el.query_selector(sel)
                if metric_el:
                    text = await metric_el.inner_text()
                    return self._parse_count(text)
            except Exception:
                continue
        return 0

    async def _extract_text(self, el, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                text_el = await el.query_selector(sel)
                if text_el:
                    return (await text_el.inner_text()).strip()
            except Exception:
                continue
        return ""

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").strip()
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0
