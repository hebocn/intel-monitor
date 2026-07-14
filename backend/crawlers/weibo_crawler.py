# intel-monitor/backend/crawlers/weibo_crawler.py
import asyncio
import json
import os
import re
import subprocess
import html as htmlmod
import logging
from pathlib import Path
from datetime import datetime as dt, timezone
from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData, parse_absolute_time

logger = logging.getLogger(__name__)

# Persistent profile directory for Weibo cookies
_PERSISTENT_PROFILE = Path(__file__).resolve().parent.parent / "data" / "weibo_profile"

# Check if autocli is available
_AUTOCLI_PATH = None
try:
    result = subprocess.run(["where", "autocli"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0 and result.stdout.strip():
        _AUTOCLI_PATH = result.stdout.strip().split("\n")[0]
except Exception:
    try:
        result = subprocess.run(["which", "autocli"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            _AUTOCLI_PATH = result.stdout.strip().split("\n")[0]
    except Exception:
        pass


async def search_weibo_via_autocli(keyword: str, limit: int = 20) -> CrawlResult:
    """Search Weibo using autocli CLI (reuses Chrome login state)."""
    if not _AUTOCLI_PATH:
        return CrawlResult(success=False, error_message="autocli 未安装，微博搜索不可用")

    def _run():
        return subprocess.run(
            [_AUTOCLI_PATH, "weibo", "search", keyword, "--format", "json", "--limit", str(limit)],
            capture_output=True, timeout=120,
        )

    try:
        proc = await asyncio.to_thread(_run)

        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            logger.warning(f"autocli weibo search failed (rc={proc.returncode}): {err[:300]}")
            if "extension is not connected" in err or "extension not connected" in err or "Chrome extension" in err:
                return CrawlResult(
                    success=False,
                    error_message="微博搜索需要 Chrome 扩展程序连接。请安装 OpenCLI Chrome 扩展并确保 Chrome 已登录微博。"
                )
            return CrawlResult(success=False, error_message=f"autocli 执行失败: {err[:200]}")

        raw = proc.stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            return CrawlResult(success=False, error_message="autocli 返回空数据")

        items = json.loads(raw)
        if not isinstance(items, list):
            return CrawlResult(success=False, error_message=f"autocli 返回格式异常: {type(items)}")

        posts = []
        for item in items:
            title = item.get("title") or item.get("text") or item.get("content") or ""
            url = item.get("url") or item.get("link") or ""
            if not title or not url:
                continue

            published_at = None
            if item.get("time"):
                published_at = parse_absolute_time(item["time"])

            posts.append(PostData(
                url=url,
                title=title[:200],
                content=item.get("content") or title[:500],
                likes=int(item.get("likes") or item.get("attitudes_count") or 0),
                comments_count=int(item.get("comments") or item.get("comments_count") or 0),
                shares=int(item.get("shares") or item.get("reposts_count") or 0),
                views=int(item.get("views") or 0),
                author_name=item.get("author") or item.get("screen_name") or "",
                author_avatar=item.get("author_avatar") or item.get("profile_image_url") or "",
                author_followers=int(item.get("author_followers") or item.get("followers_count") or 0),
                published_at=published_at,
                images=item.get("images") or [],
            ))

        logger.info(f"autocli weibo search: {len(posts)} posts for '{keyword}'")

        # Fetch hot comments for each post via Playwright (autocli returns texts, not comments)
        if posts:
            try:
                crawler = WeiboCrawler()
                await crawler.init_browser()
                await crawler.page.goto("https://m.weibo.cn/", wait_until="domcontentloaded", timeout=30000)
                await crawler.page.wait_for_timeout(3000)
                for post in posts:
                    if post.url:
                        m = re.search(r'weibo\.com/\d+/(\d+)', post.url)
                        if m:
                            mid = m.group(1)
                            try:
                                post.comments = await crawler._fetch_hot_comments_for_mid(mid)
                            except Exception:
                                pass
            except Exception:
                logger.warning("Failed to fetch hot comments via Playwright after autocli search",
                               exc_info=True)
            finally:
                await crawler.close()

        return CrawlResult(posts=posts, success=len(posts) > 0)
    except subprocess.TimeoutExpired:
        return CrawlResult(success=False, error_message="autocli 执行超时（120s）")
    except json.JSONDecodeError as e:
        return CrawlResult(success=False, error_message=f"autocli 返回无效 JSON: {e}")
    except Exception as e:
        logger.exception(f"autocli weibo search unexpected error")
        return CrawlResult(success=False, error_message=f"autocli 异常: {e}")


class WeiboCrawler(PlaywrightCrawler):
    """Weibo crawler using mobile API (m.weibo.cn)."""

    @staticmethod
    def _extract_uid(account_url: str) -> str | None:
        """Extract user ID from various Weibo URL formats."""
        # https://weibo.com/u/1643123917
        m = re.search(r'/u/(\d+)', account_url)
        if m:
            return m.group(1)
        # https://weibo.com/1643123917
        m = re.search(r'weibo\.com/(\d+)', account_url)
        if m:
            return m.group(1)
        # https://m.weibo.cn/u/1643123917
        m = re.search(r'm\.weibo\.cn/u/(\d+)', account_url)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _clean_html(text: str) -> str:
        """Convert Weibo HTML to plain text: extract img alt text, strip tags, decode entities."""
        # Remove script/iframe/style tags entirely
        text = re.sub(r'<(script|iframe|style|object|embed)\b[^>]*>[\s\S]*?</\1>', '', text, flags=re.I)
        # Replace <img alt="..."> with alt text (emoji)
        text = re.sub(r'<img[^>]+alt="([^"]*)"[^>]*>', r'\1', text)
        text = re.sub(r"<img[^>]+alt='([^']*)'[^>]*>", r'\1', text)
        # Convert <br> to space
        text = re.sub(r'<br\s*/?>', ' ', text, flags=re.I)
        # Strip remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        # Decode HTML entities
        return htmlmod.unescape(text).strip()

    async def _api_call(self, api_url: str) -> dict | None:
        """Call Weibo mobile API from page context (has cookies)."""
        result = await self.page.evaluate(f'''async () => {{
            try {{
                const resp = await fetch("{api_url}");
                return await resp.json();
            }} catch(e) {{
                return {{ error: e.message }};
            }}
        }}''')
        if result.get("error"):
            logger.warning(f"Weibo API error: {result['error']}")
            return None
        return result

    async def _fetch_long_text(self, mid: str) -> str | None:
        """Fetch full text for a truncated long post via /statuses/extend API."""
        try:
            api_url = f"https://m.weibo.cn/statuses/extend?id={mid}"
            data = await self._api_call(api_url)
            if data and data.get("ok") == 1:
                return data.get("data", {}).get("longTextContent")
        except Exception:
            pass
        return None

    async def _fetch_hot_comments_for_mid(self, mid: str) -> list[CommentData]:
        """Fetch hot comments by post mid. Browser must already be initialized and on m.weibo.cn."""
        try:
            api_url = f"https://m.weibo.cn/api/comments/hotflow?id={mid}&mid={mid}&max_id_type=0"
            data = await self._api_call(api_url)
            if not data or data.get("ok") != 1:
                return []

            comments_data = data.get("data", [])
            if isinstance(comments_data, list):
                items = comments_data
            else:
                # Some versions of the API wrap in an extra "data" key
                items = comments_data.get("data", [])
            comments = []
            for c in items[:20]:
                text = self._clean_html(c.get("text", ""))
                author = c.get("user", {}).get("screen_name", "Unknown")
                likes = c.get("like_count", 0)
                if text:
                    comments.append(CommentData(text=text, author=author, likes=likes))

            comments.sort(key=lambda c: c.likes, reverse=True)
            return comments[:10]
        except Exception:
            logger.exception(f"Failed to fetch hot comments for mid={mid}")
            return []

    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            uid = self._extract_uid(account_url)
            if not uid:
                return CrawlResult(success=False, error_message=f"Cannot extract UID from URL: {account_url}")

            await self.init_browser()

            # Visit mobile Weibo to establish cookies
            await self.page.goto("https://m.weibo.cn/", wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Fetch user profile to get containerid
            profile_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=100505{uid}"
            profile_data = await self._api_call(profile_url)
            if not profile_data or profile_data.get("ok") != 1:
                return CrawlResult(success=False, error_message="Failed to fetch Weibo profile")

            user_info = profile_data.get("data", {}).get("userInfo", {})
            screen_name = user_info.get("screen_name", "")

            # Fetch user posts
            posts_url = f"https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}"
            posts_data = await self._api_call(posts_url)
            if not posts_data:
                return CrawlResult(success=False, error_message="Failed to fetch Weibo posts")

            cards = posts_data.get("data", {}).get("cards", [])
            posts = []
            for card in cards:
                mblog = card.get("mblog")
                if not mblog:
                    continue

                text_raw = mblog.get("text", "")
                title = self._clean_html(text_raw)
                if not title:
                    continue

                mid = mblog.get("mid", "")
                post_url = f"https://weibo.com/{uid}/{mid}" if mid else ""

                # Extract image URLs (pics can be list or dict with numeric keys)
                images = []
                pics_raw = mblog.get("pics") or []
                if isinstance(pics_raw, dict):
                    pics_raw = list(pics_raw.values())
                for pic in pics_raw[:5]:
                    pic_url = pic.get("large", {}).get("url") or pic.get("url", "")
                    if pic_url:
                        images.append(pic_url)

                attitudes = self._parse_count(str(mblog.get("attitudes_count", 0)))
                comments_cnt = self._parse_count(str(mblog.get("comments_count", 0)))
                reposts = self._parse_count(str(mblog.get("reposts_count", 0)))
                created_at_str = mblog.get("created_at", "")
                author_name = mblog.get("user", {}).get("screen_name", "")
                author_avatar = mblog.get("user", {}).get("profile_image_url", "")
                author_followers = self._parse_count(str(mblog.get("user", {}).get("followers_count", 0)))
                published_at = None
                if created_at_str:
                    try:
                        published_at = dt.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
                        published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
                    except ValueError:
                        pass

                posts.append(PostData(
                    url=post_url, title=title, images=images,
                    likes=attitudes, comments_count=comments_cnt, shares=reposts,
                    author_name=author_name, author_avatar=author_avatar, author_followers=author_followers,
                    published_at=published_at,
                ))

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        try:
            m = re.search(r'weibo\.com/\d+/(\d+)', post_url)
            if not m:
                return []
            mid = m.group(1)

            await self.init_browser()
            await self.page.goto("https://m.weibo.cn/", wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(3000)

            return await self._fetch_hot_comments_for_mid(mid)
        except Exception:
            return []
        finally:
            await self.close()

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto("https://m.weibo.cn/", wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(3000)

            from urllib.parse import quote
            encoded_kw = quote(keyword)
            posts = []

            for page in range(1, 11):
                search_url = f"https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D60%26q%3D{encoded_kw}&page={page}"
                search_data = await self._api_call(search_url)
                if not search_data or search_data.get("ok") != 1:
                    break

                cards = search_data.get("data", {}).get("cards", [])
                if not cards:
                    break

                for card in cards:
                    mblog = card.get("mblog")
                    if not mblog:
                        continue

                    text_raw = mblog.get("text", "")
                    mid = mblog.get("mid", "")
                    # Expand long text if truncated by the search API
                    if mblog.get("isLongText") and mid:
                        long_text = await self._fetch_long_text(mid)
                        if long_text:
                            text_raw = long_text
                    title = self._clean_html(text_raw)
                    if not title:
                        continue

                    uid = str(mblog.get("user", {}).get("id", ""))
                    post_url = f"https://weibo.com/{uid}/{mid}" if mid and uid else ""

                    images = []
                    pics_raw = mblog.get("pics") or []
                    if isinstance(pics_raw, dict):
                        pics_raw = list(pics_raw.values())
                    for pic in pics_raw[:5]:
                        pic_url = pic.get("large", {}).get("url") or pic.get("url", "")
                        if pic_url:
                            images.append(pic_url)

                    videos = []
                    page_info = mblog.get("page_info")
                    if page_info and str(page_info.get("object_type", "")) == "11":
                        vid_url = page_info.get("page_url", "")
                        if vid_url:
                            videos.append({"url": vid_url, "play_count": page_info.get("play_count", "")})

                    attitudes = self._parse_count(str(mblog.get("attitudes_count", 0)))
                    comments_cnt = self._parse_count(str(mblog.get("comments_count", 0)))
                    reposts = self._parse_count(str(mblog.get("reposts_count", 0)))
                    created_at_str = mblog.get("created_at", "")
                    author_name = mblog.get("user", {}).get("screen_name", "")
                    author_avatar = mblog.get("user", {}).get("profile_image_url", "")
                    author_followers = self._parse_count(str(mblog.get("user", {}).get("followers_count", 0)))
                    published_at = None
                    if created_at_str:
                        try:
                            published_at = dt.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
                            published_at = published_at.astimezone(timezone.utc).replace(tzinfo=None)
                        except ValueError:
                            pass

                    posts.append(PostData(
                        url=post_url, title=title, content=title, images=images, videos=videos,
                        likes=attitudes, comments_count=comments_cnt, shares=reposts,
                        author_name=author_name, author_avatar=author_avatar, author_followers=author_followers,
                        published_at=published_at,
                    ))
                    if len(posts) >= limit:
                        break

                if len(posts) >= limit:
                    break

            # Fetch hot comments for each post (reuse existing browser)
            for post in posts:
                if post.url:
                    m = re.search(r'weibo\.com/\d+/(\d+)', post.url)
                    if m:
                        mid = m.group(1)
                        try:
                            post.comments = await self._fetch_hot_comments_for_mid(mid)
                        except Exception:
                            pass

            return CrawlResult(posts=posts, success=len(posts) > 0)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
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
