import re
from datetime import datetime, timezone
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData


class XCrawler(PlaywrightCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="domcontentloaded", timeout=20000)
            await self.page.wait_for_timeout(3000)

            # Check if login wall
            content = await self.page.content()
            if "Log in" in content and "Sign up" in content and 'data-testid="tweet"' not in content:
                return CrawlResult(
                    success=False,
                    error_message="X (Twitter) 需要登录才能查看，请使用网站监控代替",
                )

            # Scroll to load more tweets
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 800)")
                await self.page.wait_for_timeout(1500)

            # Extract tweets
            tweet_elements = await self.page.query_selector_all('article[data-testid="tweet"]')
            posts = []
            for el in tweet_elements[:10]:
                try:
                    text_el = await el.query_selector('[data-testid="tweetText"]')
                    if text_el:
                        text = await text_el.inner_html()
                        # Remove dangerous tags/attributes
                        text = re.sub(r'<(script|iframe|style|object|embed)\b[^>]*>[\s\S]*?</\1>', '', text, flags=re.I)
                        text = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', '', text, flags=re.I)
                        text = re.sub(r"\s+on\w+\s*=\s*'[^']*'", '', text, flags=re.I)
                    else:
                        text = ""

                    link_el = await el.query_selector('a[href*="/status/"]')
                    href = await link_el.get_attribute("href") if link_el else ""
                    url = f"https://x.com{href}" if href else ""

                    like_el = await el.query_selector('[data-testid="like"] span')
                    likes_text = await like_el.inner_text() if like_el else "0"
                    likes = self._parse_count(likes_text)

                    published_at = None
                    time_el = await el.query_selector('time[datetime]')
                    if time_el:
                        time_str = await time_el.get_attribute('datetime')
                        if time_str:
                            try:
                                published_at = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                                published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
                            except (ValueError, TypeError):
                                pass

                    if text:
                        posts.append(PostData(url=url, content=text, likes=likes, published_at=published_at))
                except Exception:
                    continue

            if not posts:
                return CrawlResult(
                    success=False,
                    error_message="未找到推文，可能需要登录或页面结构已变化",
                )

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            error_msg = str(e)
            if "Timeout" in error_msg:
                error_msg = "页面加载超时，请检查网络连接"
            elif "net::ERR" in error_msg:
                error_msg = "网络连接失败，请检查网络"
            return CrawlResult(success=False, error_message=error_msg)
        finally:
            await self.close()

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            await self.page.wait_for_timeout(3000)

            replies = await self.page.query_selector_all('article[data-testid="tweet"]')
            comments = []
            for reply in replies[:20]:
                try:
                    text_el = await reply.query_selector('[data-testid="tweetText"]')
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await reply.query_selector('[data-testid="User-Name"] span')
                    author = await author_el.inner_text() if author_el else "Unknown"

                    like_el = await reply.query_selector('[data-testid="like"] span')
                    likes_text = await like_el.inner_text() if like_el else "0"
                    likes = self._parse_count(likes_text)

                    if text:
                        comments.append(CommentData(text=text, author=author, likes=likes))
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
        text = text.strip().replace(",", "")
        if "K" in text:
            return int(float(text.replace("K", "")) * 1000)
        if "M" in text:
            return int(float(text.replace("M", "")) * 1000000)
        try:
            return int(text)
        except ValueError:
            return 0
