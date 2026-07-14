# intel-monitor/backend/crawlers/douyin_crawler.py
import os
from urllib.parse import quote
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData, parse_relative_time, parse_absolute_time


CDP_URL = os.getenv("CHROME_CDP_URL", "http://localhost:9222")


class DouyinCrawler(PlaywrightCrawler):
    """Douyin crawler using CDP connection to reuse user's logged-in Chrome."""

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
        # Use existing first page from default context to preserve full session
        contexts = self.browser.contexts
        if contexts and contexts[0].pages:
            self.page = contexts[0].pages[0]
        elif contexts:
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
        # Don't close browser — it's the user's Chrome

    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await self.page.wait_for_timeout(1500)

            video_elements = await self.page.query_selector_all(
                'li[class*="item"], div[class*="video-card"], a[href*="/video/"]'
            )
            posts = []
            for el in video_elements[:10]:
                try:
                    title_el = await el.query_selector('p, .title, span[class*="title"]')
                    title = await title_el.inner_text() if title_el else ""

                    href = await el.get_attribute("href") or ""
                    url = f"https://www.douyin.com{href}" if href.startswith("/") else href

                    time_text = await self._extract_text(el, [
                        'span[class*="time"]', '.time', 'span:last-child',
                    ])
                    published_at = parse_relative_time(time_text) or parse_absolute_time(time_text)

                    if title and title.strip():
                        posts.append(PostData(url=url, title=title.strip(), published_at=published_at))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        try:
            await self.init_browser()
            # First visit main page to establish session before search
            await self.page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(4000)
            encoded_kw = quote(keyword)
            search_url = f"https://www.douyin.com/search/{encoded_kw}"
            await self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(8000)

            for _ in range(5):
                await self.page.evaluate("window.scrollBy(0, 1000)")
                await self.page.wait_for_timeout(2000)

            # Inject JS to extract any visible search result content
            raw_items = await self.page.evaluate('''() => {
                const items = [];
                // Find all links that might be search results
                const allLinks = document.querySelectorAll("a[href]");
                const seen = new Set();
                for (const a of allLinks) {
                    const href = a.href || "";
                    const text = (a.innerText || "").trim();
                    // Skip nav/footer links, empty text
                    if (!text || text.length < 5 || text.length > 500) continue;
                    if (seen.has(href)) continue;
                    seen.add(href);
                    // Look for video/user links
                    if (href.includes("/video/") || href.includes("/user/") || href.includes("/note/")) {
                        // Get the parent container for context
                        const parent = a.closest("div[class], li[class]") || a.parentElement;
                        const parentText = (parent?.innerText || "").trim();
                        items.push({
                            title: text.substring(0, 400),
                            url: href,
                            fullText: parentText.substring(0, 600),
                            className: (parent?.className || "").substring(0, 100)
                        });
                    }
                }
                // Also look for any element containing the keyword
                if (items.length === 0) {
                    const body = document.body.innerText;
                    const keyword = decodeURIComponent(window.location.pathname.split("/").pop() || "");
                    for (const div of document.querySelectorAll("div")) {
                        const text = (div.innerText || "").trim();
                        if (text.length > 20 && text.length < 500 && div.querySelector("a")) {
                            const links = div.querySelectorAll("a[href*=\\"/video/\\"], a[href*=\\"/user/\\"]");
                            if (links.length > 0) {
                                items.push({
                                    title: text.substring(0, 400),
                                    url: links[0].href,
                                    fullText: text.substring(0, 600),
                                    className: (div.className || "").substring(0, 100)
                                });
                            }
                        }
                    }
                }
                return items.slice(0, 30);
            }''')

            posts = []
            for item in raw_items[:limit]:
                title = item.get("title", "")
                url = item.get("url", "")
                if title and url:
                    posts.append(PostData(
                        url=url, title=title, content=title,
                        author_name="",
                    ))

            return CrawlResult(posts=posts, success=len(posts) > 0)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

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

    async def get_hot_comments(self, video_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(video_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            comment_elements = await self.page.query_selector_all('div[class*="comment"], li[class*="comment"]')
            comments = []
            for el in comment_elements[:20]:
                try:
                    text_el = await el.query_selector('span[class*="text"], p, .content')
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await el.query_selector('span[class*="name"], .author, .nickname')
                    author = await author_el.inner_text() if author_el else "Unknown"

                    likes_el = await el.query_selector('span[class*="like"], .like-count')
                    likes_text = await likes_el.inner_text() if likes_el else "0"
                    likes = self._parse_count(likes_text.strip())

                    if text:
                        comments.append(CommentData(text=text, author=author.strip(), likes=likes))
                except Exception:
                    continue

            comments.sort(key=lambda c: c.likes, reverse=True)
            return comments[:10]
        except Exception:
            return []
        finally:
            await self.close()

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").strip()
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0
