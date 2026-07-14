# intel-monitor/backend/crawlers/youtube_crawler.py
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData, parse_relative_time


class YouTubeCrawler(PlaywrightCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            # Navigate to videos tab
            videos_url = account_url.rstrip("/") + "/videos"
            await self.page.goto(videos_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load more
            for _ in range(2):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await self.page.wait_for_timeout(1000)

            # Get video elements
            video_elements = await self.page.query_selector_all("ytd-rich-item-renderer")
            posts = []
            for el in video_elements[:10]:
                try:
                    title_el = await el.query_selector("#video-title")
                    title = await title_el.inner_text() if title_el else ""
                    href = await title_el.get_attribute("href") if title_el else ""
                    url = f"https://www.youtube.com{href}" if href else ""

                    views_el = await el.query_selector("#metadata-line span")
                    views = await views_el.inner_text() if views_el else ""

                    # Extract relative time from second metadata span (e.g. "3 days ago")
                    published_at = None
                    metadata_spans = await el.query_selector_all("#metadata-line span")
                    for span in metadata_spans[1:]:
                        span_text = await span.inner_text()
                        if "ago" in span_text.lower():
                            published_at = parse_relative_time(span_text)
                            if published_at:
                                break

                    if title:
                        posts.append(PostData(url=url, title=title.strip(), content=views.strip(), published_at=published_at))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, video_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(video_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to comments section
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 500)")
                await self.page.wait_for_timeout(1000)

            comment_elements = await self.page.query_selector_all("ytd-comment-thread-renderer")
            comments = []
            for el in comment_elements[:20]:
                try:
                    text_el = await el.query_selector("#content-text")
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await el.query_selector("#author-text span")
                    author = await author_el.inner_text() if author_el else "Unknown"

                    likes_el = await el.query_selector("#vote-count-middle")
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
        if not text:
            return 0
        try:
            return int(text)
        except ValueError:
            return 0
