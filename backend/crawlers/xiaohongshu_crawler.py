# intel-monitor/backend/crawlers/xiaohongshu_crawler.py
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData


class XiaoHongShuCrawler(PlaywrightCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load notes
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await self.page.wait_for_timeout(1500)

            # Get note elements
            note_elements = await self.page.query_selector_all('section.note-item, div.note-item, a[href*="/explore/"]')
            posts = []
            for el in note_elements[:10]:
                try:
                    title_el = await el.query_selector('.title, .note-title, span')
                    title = await title_el.inner_text() if title_el else ""

                    href = await el.get_attribute("href") or ""
                    url = f"https://www.xiaohongshu.com{href}" if href.startswith("/") else href

                    if title and title.strip():
                        posts.append(PostData(url=url, title=title.strip()))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, note_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(note_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            comment_elements = await self.page.query_selector_all('.comment-item, div[class*="comment"]')
            comments = []
            for el in comment_elements[:20]:
                try:
                    text_el = await el.query_selector('.content, .comment-text, p')
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await el.query_selector('.author, .nickname, .name')
                    author = await author_el.inner_text() if author_el else "Unknown"

                    likes_el = await el.query_selector('.like-count, .likes, span[class*="like"]')
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
