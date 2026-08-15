# intel-monitor/backend/crawlers/opencli_crawler.py
"""
OpenCLI 爬虫 - 通过 opencli CLI 调用平台适配器
复用用户已登录的 Chrome 浏览器，无需额外凭证
"""
import asyncio
import json
import logging
import re
import shutil
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from crawlers.base import PlaywrightCrawler, CrawlResult, PostData, CommentData
from crawlers.router import CrawlerEntry

# 平台命令映射: platform_key -> (opencli_site, command_name)
PLATFORM_CMD = {
    "x": ("twitter", "tweets"),
    "weibo": ("weibo", "user-posts"),
    "xiaohongshu": ("xiaohongshu", "search"),
    "reddit": ("reddit", "hot"),
    "bilibili": ("bilibili", "hot"),
}
def _check_opencli() -> bool:
    return shutil.which("opencli") is not None


def _extract_username(platform: str, account_url: str, account_name: str) -> str:
    if platform == "xiaohongshu":
        return account_name.strip()

    if account_url:
        parsed = urlparse(account_url)
        path = parsed.path.strip("/")
        if path:
            return path.split("/")[0]

    return account_name.strip()


def _parse_count(text: str) -> int:
    text = text.strip().replace(",", "")
    if not text:
        return 0
    if "K" in text:
        return int(float(text.replace("K", "")) * 1000)
    if "M" in text:
        return int(float(text.replace("M", "")) * 1000000)
    if "万" in text:
        return int(float(text.replace("万", "")) * 10000)
    try:
        return int(text)
    except ValueError:
        return 0


def _extract_image_urls(item: dict, max_images: int = 5) -> list[str]:
    """从 OpenCLI 返回的帖子 JSON 中提取图片 URL，尝试多种常见字段名。"""
    urls = []
    for field_name in ("media", "media_urls", "photos", "images", "image_list"):
        media = item.get(field_name, [])
        if not isinstance(media, list):
            continue
        for m in media:
            if isinstance(m, dict):
                url = m.get("url", "") or m.get("src", "") or m.get("media_url_https", "")
                media_type = m.get("type", "photo")
                if url and media_type in ("photo", "image", ""):
                    urls.append(url)
            elif isinstance(m, str) and m.startswith("http"):
                # Skip video URLs (mp4, mov, etc.) — only include image URLs
                ext_match = re.search(r"\.(mp4|mov|avi|webm|mkv|flv)(\?|$)", m.lower())
                if not ext_match:
                    urls.append(m)
        if urls:
            break
    # 单独尝试 cover 字段（小红书等）
    if not urls:
        cover = item.get("cover", "")
        if isinstance(cover, str) and cover.startswith("http"):
            urls.append(cover)
    # 尝试 pic 字段（Bilibili 等）
    if not urls:
        pic = item.get("pic", "")
        if isinstance(pic, str) and pic.startswith("http"):
            urls.append(pic)
    return urls[:max_images]


def _parse_twitter_posts(data) -> list[PostData]:
    posts = []
    items = data if isinstance(data, list) else [data]

    for item in items:
        try:
            if isinstance(item, dict):
                text = item.get("text", "") or item.get("full_text", "")
                tweet_id = item.get("id", "")
                author = item.get("author", "")
                url = f"https://x.com/{author}/status/{tweet_id}" if tweet_id and author else ""
                likes = int(item.get("likes", 0) or 0)
                views = int(item.get("views", 0) or 0)
                shares = int(item.get("retweets", 0) or 0)
                comments_count = int(item.get("replies", 0) or 0)
                bookmarks = int(item.get("bookmarks", 0) or 0)
                author_name = item.get("name", "") or ""
                author_avatar = item.get("avatar", "") or ""
                images = _extract_image_urls(item)
                quoted_tweet = item.get("quoted_tweet") or None
                card = item.get("card") or None

                # Parse created_at to published_at (format: "Wed Jul 15 18:57:47 +0000 2026")
                published_at = None
                created_at_str = item.get("created_at", "")
                if created_at_str:
                    try:
                        from datetime import datetime
                        published_at = datetime.strptime(
                            created_at_str, "%a %b %d %H:%M:%S %z %Y"
                        ).replace(tzinfo=None)
                    except Exception:
                        pass

                posts.append(PostData(
                    url=url, content=text, likes=likes, views=views,
                    shares=shares, comments_count=comments_count,
                    bookmarks=bookmarks, author_name=author_name,
                    author_avatar=author_avatar, author_followers=0,
                    published_at=published_at, images=images,
                    quoted_tweet=quoted_tweet, card=card,
                ))
        except Exception:
            continue

    return posts


def _parse_reddit_posts(data) -> list[PostData]:
    posts = []
    items = data if isinstance(data, list) else [data]

    for item in items[:10]:
        try:
            if isinstance(item, dict):
                title = item.get("title", "")
                url = item.get("url", "") or item.get("permalink", "")
                if url and not url.startswith("http"):
                    url = "https://reddit.com" + url
                score = int(item.get("score", 0) or 0)
                images = _extract_image_urls(item)
                posts.append(PostData(url=url, title=title, content=title, likes=score, images=images))
        except Exception:
            continue

    return posts


def _parse_bilibili_posts(data) -> list[PostData]:
    posts = []
    items = data if isinstance(data, list) else [data]

    for item in items[:10]:
        try:
            if isinstance(item, dict):
                title = item.get("title", "")
                url = item.get("url", "") or item.get("link", "")
                if not url.startswith("http"):
                    bvid = item.get("bvid", "")
                    url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
                play = int(item.get("play", 0) or 0)
                images = _extract_image_urls(item)
                posts.append(PostData(url=url, title=title, content=title, likes=play, images=images))
        except Exception:
            continue

    return posts


def _parse_xiaohongshu_posts(data) -> list[PostData]:
    posts = []
    items = data if isinstance(data, list) else [data]

    for item in items[:10]:
        try:
            if isinstance(item, dict):
                title = item.get("title", "")
                url = item.get("url", "") or ""
                likes = _parse_count(str(item.get("likes", "0")))
                images = _extract_image_urls(item)
                posts.append(PostData(url=url, title=title, content=title, likes=likes, images=images))
        except Exception:
            continue

    return posts


def _parse_weibo_posts(data) -> list[PostData]:
    """解析 opencli weibo user-posts 输出（正文/转发/评论/点赞/链接）。"""
    posts = []
    items = data if isinstance(data, list) else [data]
    for item in items:
        try:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "") or ""
            url = item.get("url", "") or ""
            likes = int(item.get("likes", 0) or 0)
            comments_count = int(item.get("comments", 0) or 0)
            shares = int(item.get("reposts", 0) or 0)
            author = item.get("author", "") or ""
            uid = item.get("uid", "") or ""
            published_at = None
            time_str = item.get("time", "") or ""
            if time_str:
                try:
                    from datetime import datetime
                    # 微博时间格式: "Wed Jul 15 18:57:47 +0800 2026" 或类似
                    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%a %b %d %H:%M:%S %Y"):
                        try:
                            published_at = datetime.strptime(time_str, fmt).replace(tzinfo=None)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            posts.append(PostData(
                url=url, content=text, title=text[:80],
                likes=likes, comments_count=comments_count, shares=shares,
                author_name=author,
                published_at=published_at, images=[],
            ))
        except Exception:
            continue
    return posts


def _parse_posts(platform: str, data) -> list[PostData]:
    parsers = {
        "x": _parse_twitter_posts,
        "weibo": _parse_weibo_posts,
        "xiaohongshu": _parse_xiaohongshu_posts,
        "reddit": _parse_reddit_posts,
        "bilibili": _parse_bilibili_posts,
    }
    parser = parsers.get(platform, _parse_twitter_posts)
    posts = parser(data)
    img_total = sum(len(p.images) for p in posts)
    if img_total > 0:
        logger.info(f"[OpenCLI] {platform} 解析: {len(posts)} 条帖子, {img_total} 张图片")
    else:
        logger.info(f"[OpenCLI] {platform} 解析: {len(posts)} 条帖子, 无图片")
    return posts


class OpenCLIError(Exception):
    """_run_opencli 失败时抛出的异常"""


async def _run_opencli(platform: str, username_or_query: str, limit: int = 10, is_search: bool = False):
    """运行 opencli 命令并返回解析后的 JSON。失败时抛出 OpenCLIError。

    is_search=True: 使用 search 子命令（如 opencli twitter search <query>）
    is_search=False: 使用默认命令爬取账号（如 opencli twitter tweets <username>）
    """
    import subprocess as _sp

    site, cmd = PLATFORM_CMD.get(platform, (None, None))
    if not site:
        raise OpenCLIError(f"不支持的平台: {platform}")

    opencli_path = shutil.which("opencli")
    if not opencli_path:
        raise OpenCLIError("opencli 命令未找到")

    if is_search and platform == "x":
        args = [site, "search", username_or_query]
    else:
        args = [site, cmd]
        if platform in ("x", "weibo", "xiaohongshu"):
            args.append(username_or_query)
    args.extend(["--limit", str(limit), "--format", "json"])

    # 大条数抓取需要更长超时：粗估每条约 0.3s（X 分页含 2s/页节流），上限 900s
    subprocess_timeout = min(900, max(120, int(limit * 0.3)))

    def _run_subprocess():
        """Run opencli in a thread to avoid event loop subprocess issues on Windows."""
        try:
            result = _sp.run(
                [opencli_path] + args,
                capture_output=True,
                timeout=subprocess_timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except _sp.TimeoutExpired:
            raise OpenCLIError("OpenCLI 执行超时")
        except Exception as e:
            raise OpenCLIError(str(e) or type(e).__name__)

    last_error = None
    for attempt in range(3):
        try:
            stdout, stderr, returncode = await asyncio.to_thread(_run_subprocess)
            raw = stdout.decode("utf-8", errors="ignore").strip()
            err = stderr.decode("utf-8", errors="ignore").strip()

            if returncode != 0:
                msg = f"OpenCLI 返回非零退出码 ({returncode}): {err[:200]}"
                if attempt < 2:
                    last_error = msg
                    await asyncio.sleep(2)
                    continue
                raise OpenCLIError(msg)

            # 提取 JSON
            start = raw.find("[")
            if start < 0:
                start = raw.find("{")
            if start >= 0:
                raw = raw[start:]

            data = json.loads(raw) if raw else None
            if not data:
                msg = "OpenCLI 返回空数据"
                if attempt < 2:
                    last_error = msg
                    await asyncio.sleep(2)
                    continue
                raise OpenCLIError(msg)

            return data

        except (OpenCLIError, json.JSONDecodeError):
            raise
        except Exception as e:
            msg = str(e) or type(e).__name__
            if attempt < 2:
                last_error = msg
                await asyncio.sleep(2)
                continue
            raise OpenCLIError(msg)

    raise OpenCLIError(last_error or "OpenCLI 失败")


async def _run_opencli_thread(tweet_id: str) -> list:
    """运行 opencli twitter thread <tweet-id> 并返回 JSON（原帖 + 全部回复）。

    复用 Chrome 登录态（Browser Bridge），失败时抛出 OpenCLIError。
    """
    import subprocess as _sp

    opencli_path = shutil.which("opencli")
    if not opencli_path:
        raise OpenCLIError("opencli 命令未找到")

    args = ["twitter", "thread", tweet_id, "--format", "json"]

    def _run_subprocess():
        try:
            result = _sp.run(
                [opencli_path] + args,
                capture_output=True,
                timeout=120,
            )
            return result.stdout, result.stderr, result.returncode
        except _sp.TimeoutExpired:
            raise OpenCLIError("OpenCLI thread 执行超时")
        except Exception as e:
            raise OpenCLIError(str(e) or type(e).__name__)

    stdout, stderr, returncode = await asyncio.to_thread(_run_subprocess)
    raw = stdout.decode("utf-8", errors="ignore").strip()
    err = stderr.decode("utf-8", errors="ignore").strip()

    if returncode != 0:
        raise OpenCLIError(f"OpenCLI thread 返回非零退出码 ({returncode}): {err[:200]}")

    start = raw.find("[")
    if start < 0:
        start = raw.find("{")
    if start < 0:
        raise OpenCLIError("OpenCLI thread 返回数据中未找到 JSON")

    data = json.loads(raw[start:])
    return data if isinstance(data, list) else []


class OpenCLICrawler(PlaywrightCrawler):

    def __init__(self, platform: str = ""):
        super().__init__()
        self.platform = platform

    async def crawl(self, account_url: str) -> CrawlResult:
        if not _check_opencli():
            return CrawlResult(
                success=False,
                error_message="OpenCLI 未安装，请运行: npm install -g @jackwener/opencli"
            )

        platform = self.platform or "x"
        username = _extract_username(platform, account_url, "")

        try:
            data = await _run_opencli(platform, username)
            posts = _parse_posts(platform, data)

            if not posts:
                return CrawlResult(
                    success=False,
                    error_message="未提取到内容，可能需要登录或命令参数不正确"
                )

            return CrawlResult(posts=posts, success=True)

        except OpenCLIError as e:
            return CrawlResult(success=False, error_message=str(e))
        except Exception as e:
            return CrawlResult(success=False, error_message=f"OpenCLI 爬取失败: {str(e) or type(e).__name__}")

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        """通过 opencli twitter thread 抓取帖文回复（评论）。

        复用 Chrome 登录态，返回原帖的所有回复（带 likes/retweets）。
        非 twitter 平台或无帖文 ID 时返回空列表。
        """
        if self.platform != "x":
            return []
        m = re.search(r'/status/(\d+)', post_url)
        if not m:
            return []
        tweet_id = m.group(1)

        try:
            data = await _run_opencli_thread(tweet_id)
            if not isinstance(data, list):
                return []

            comments = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                text = item.get("text", "") or ""
                # 第一条是原帖（无 in_reply_to），跳过；只保留该帖的直接回复
                if not item.get("in_reply_to"):
                    continue
                if not text:
                    continue
                comments.append(CommentData(
                    text=text,
                    author=item.get("author", "Unknown"),
                    likes=int(item.get("likes", 0) or 0),
                    retweet_count=int(item.get("retweets", 0) or 0),
                    url=item.get("url", ""),
                ))

            comments.sort(key=lambda c: c.likes + c.retweet_count * 2, reverse=True)
            return comments[:10]
        except OpenCLIError as e:
            logger.warning(f"[OpenCLI] 抓取帖文评论失败: {post_url} ({e})")
            return []
        except Exception as e:
            logger.warning(f"[OpenCLI] 抓取帖文评论异常: {post_url} ({type(e).__name__}: {e})")
            return []


async def crawl_with_opencli(platform: str, account_name: str, account_url: str, limit: int = 10) -> CrawlResult:
    crawler = OpenCLICrawler(platform=platform)
    username = _extract_username(platform, account_url, account_name)

    if not _check_opencli():
        return CrawlResult(
            success=False,
            error_message="OpenCLI 未安装，请运行: npm install -g @jackwener/opencli"
        )

    try:
        data = await _run_opencli(platform, username, limit=limit)
        posts = _parse_posts(platform, data)

        if not posts:
            return CrawlResult(
                success=False,
                error_message="未提取到内容"
            )

        return CrawlResult(posts=posts, success=True)

    except OpenCLIError as e:
        return CrawlResult(success=False, error_message=str(e))
    except Exception as e:
        return CrawlResult(success=False, error_message=str(e) or type(e).__name__)


async def search_x_via_opencli(keyword: str, limit: int = 10) -> CrawlResult:
    """搜索 X/Twitter 关键词。通过 OpenCLI 复用 Chrome 登录态。

    Returns CrawlResult with posts on success.
    """
    if not _check_opencli():
        return CrawlResult(
            success=False,
            error_message="OpenCLI 未安装，请运行: npm install -g @jackwener/opencli"
        )

    try:
        data = await _run_opencli("x", keyword, limit=limit, is_search=True)
        posts = _parse_posts("x", data)

        if not posts:
            return CrawlResult(
                success=False,
                error_message="未搜索到 X 相关内容"
            )

        return CrawlResult(posts=posts, success=True)

    except OpenCLIError as e:
        return CrawlResult(success=False, error_message=str(e))
    except Exception as e:
        return CrawlResult(success=False, error_message=str(e) or type(e).__name__)


def build_opencli_entry() -> CrawlerEntry:
    async def _check():
        return _check_opencli()

    async def _crawl(platform, account_name, account_url, post_limit=10):
        return await crawl_with_opencli(platform, account_name, account_url, limit=post_limit)

    return CrawlerEntry(
        name="opencli",
        platforms=frozenset(PLATFORM_CMD.keys()),
        crawl=_crawl,
        available=_check,
    )
