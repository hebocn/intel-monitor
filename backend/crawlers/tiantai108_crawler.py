# intel-monitor/backend/crawlers/tiantai108_crawler.py
import re
import logging
from urllib.parse import quote
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData, parse_absolute_time

logger = logging.getLogger(__name__)


class Tiantai108Crawler(PlaywrightCrawler):
    """108sq.cn (天台社区) crawler using search page DOM parsing.

    The site is server-rendered with JS-enhanced search. Strategy:
    1. Try direct URL-based search first: /search?keyword=xxx
    2. If that fails, fall back to CDP-assisted search (click icon → type → submit)
    """

    BASE_URL = "https://tiantai.108sq.cn"

    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)
            return await self._parse_post_list(20)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        try:
            await self.init_browser()

            # Strategy 1: Try GET search URL patterns
            encoded_kw = quote(keyword)
            for search_pattern in [
                f"{self.BASE_URL}/search?keyword={encoded_kw}",
                f"{self.BASE_URL}/search?q={encoded_kw}",
                f"{self.BASE_URL}/search/{encoded_kw}",
                f"{self.BASE_URL}/search?key={encoded_kw}",
            ]:
                try:
                    await self.page.goto(search_pattern, wait_until="networkidle", timeout=15000)
                    await self.page.wait_for_timeout(2000)
                    content = await self.page.content()
                    if keyword in content and ("post" in content.lower() or "thread" in content.lower() or "帖子" in content):
                        return await self._parse_post_list(limit)
                except Exception:
                    continue

            # Strategy 2: CDP-assisted search — click search icon, type, submit
            await self.page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(2000)

            # Click search icon
            search_icon_selectors = ['img[src*="search"]', '.search-icon', '[class*="search"]', 'a:has(img[src*="search"])']
            clicked = False
            for sel in search_icon_selectors:
                try:
                    icon = await self.page.query_selector(sel)
                    if icon:
                        await icon.click()
                        await self.page.wait_for_timeout(1000)
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                # Try clicking the javascript:void(0) link directly
                try:
                    await self.page.evaluate('''() => {
                        const links = document.querySelectorAll('a[href="javascript:void(0);"]');
                        for (const link of links) {
                            const img = link.querySelector('img[src*="search"]');
                            if (img) { link.click(); return true; }
                        }
                        return false;
                    }''')
                    await self.page.wait_for_timeout(1000)
                except Exception:
                    pass

            # Type keyword into search input
            input_selectors = ['input[type="text"]', 'input[name*="search"]', 'input[name*="keyword"]', 'input[name="q"]', 'input.search-input', 'input']
            for sel in input_selectors:
                try:
                    search_input = await self.page.query_selector(sel)
                    if search_input:
                        await search_input.fill(keyword)
                        await search_input.press("Enter")
                        await self.page.wait_for_timeout(3000)
                        break
                except Exception:
                    continue

            return await self._parse_post_list(limit)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def _parse_post_list(self, limit: int) -> CrawlResult:
        posts = []

        post_selectors = [
            '.post-item', '.thread-item', 'li[class*="post"]', 'div[class*="post"]',
            '.topic-item', 'a[href*="thread"]', 'a[href*="topic"]', 'a[href*="post"]',
            'div[class*="list"] > div', 'table[class*="list"] tr',
        ]

        elements = []
        for sel in post_selectors:
            elements = await self.page.query_selector_all(sel)
            if len(elements) >= 1:
                break

        for el in elements[:limit]:
            try:
                title_el = await el.query_selector('a, .title, .subject, h3, h4, span[class*="title"]')
                title = await title_el.inner_text() if title_el else ""

                href = ""
                try:
                    href = await title_el.get_attribute("href") if title_el else ""
                except Exception:
                    href = await el.get_attribute("href") or ""

                if href and href.startswith("/"):
                    url = f"{self.BASE_URL}{href}"
                elif href:
                    url = href
                else:
                    url = ""

                # This platform only shows comment counts
                comments = 0
                for metric_sel in ['span:last-child', '.reply-count', '.comment-count', 'em', '.count']:
                    try:
                        metric_el = await el.query_selector(metric_sel)
                        if metric_el:
                            text = await metric_el.inner_text()
                            comments = self._parse_count(text)
                            if comments > 0:
                                break
                    except Exception:
                        continue

                author = ""
                for author_sel in ['.author', '.poster', 'span[class*="user"]', '.username']:
                    try:
                        author_el = await el.query_selector(author_sel)
                        if author_el:
                            author = (await author_el.inner_text()).strip()
                            break
                    except Exception:
                        continue

                time_text = ""
                for time_sel in ['td:last-child', '.time', '.date', 'span[class*="time"]', 'td[class*="time"]']:
                    try:
                        time_el = await el.query_selector(time_sel)
                        if time_el:
                            time_text = (await time_el.inner_text()).strip()
                            if time_text and any(c.isdigit() for c in time_text):
                                break
                            time_text = ""
                    except Exception:
                        continue
                published_at = parse_absolute_time(time_text)

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

    @staticmethod
    def _parse_count(text: str) -> int:
        text = re.sub(r'[\[\]]', '', text).replace(",", "").strip()
        try:
            return int(text)
        except ValueError:
            return 0
