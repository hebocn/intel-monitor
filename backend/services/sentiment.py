# intel-monitor/backend/services/sentiment.py
import asyncio
import json
import logging
import shutil
from datetime import datetime

from sqlalchemy import select
from database import async_session
from models.sentiment_task import SentimentTask
from models.sentiment_post import SentimentPost
from crawlers.base import _run_crawler_in_thread
from crawlers.weibo_crawler import WeiboCrawler, search_weibo_via_autocli
from crawlers.douyin_crawler import DouyinCrawler
from crawlers.toutiao_crawler import ToutiaoCrawler
from crawlers.toutiao_scrapling_crawler import ToutiaoScraplingCrawler
from crawlers.tiantai108_crawler import Tiantai108Crawler
from crawlers.opencli_crawler import search_x_via_opencli
from crawlers.youtube_search import search_youtube
from services.scoring import (
    calculate_impact, get_platform_stats_dict, get_platform_all_values,
    PLATFORM_MAU_DEFAULTS, DEFAULT_HALF_LIFE_DAYS,
)

logger = logging.getLogger(__name__)


async def run_sentiment_search(task_id: int, keyword: str, platforms: list[str],
                                post_limit: int = 20, half_life_days: float = DEFAULT_HALF_LIFE_DAYS):
    """Background task: search all platforms concurrently, score, and store results."""
    async with async_session() as db:
        task = await db.get(SentimentTask, task_id)
        if not task:
            logger.error(f"SentimentTask {task_id} not found")
            return
        task.status = "running"
        await db.commit()

        error_log = {}
        all_posts = []
        stats_dict = await get_platform_stats_dict(db)
        all_values = await get_platform_all_values(db)

        # Concurrent search across all platforms
        async def search_platform(platform: str):
            try:
                crawler = None
                if platform == "weibo":
                    # Try autocli first (reuses Chrome login), fall back to Playwright
                    result = await search_weibo_via_autocli(keyword, limit=post_limit)
                    if not result.success:
                        logger.warning(f"Weibo autocli failed: {result.error_message}, trying Playwright fallback...")
                        crawler = WeiboCrawler()
                        result = await _run_crawler_in_thread(crawler.search_by_keyword(keyword, limit=post_limit))
                elif platform == "douyin":
                    crawler = DouyinCrawler()
                    result = await crawler.search_by_keyword(keyword, limit=post_limit)
                elif platform == "xiaohongshu":
                    result = await _search_xiaohongshu(keyword, post_limit)
                elif platform == "toutiao":
                    # Try CDP first (reuses Chrome login), fall back to Scrapling
                    result = await _search_toutiao(keyword, post_limit)
                elif platform == "108community":
                    crawler = Tiantai108Crawler()
                    result = await _run_crawler_in_thread(crawler.search_by_keyword(keyword, limit=post_limit))
                elif platform == "youtube":
                    result = await search_youtube(keyword, limit=post_limit)
                    if result.success and result.posts:
                        await _generate_youtube_summaries(result.posts)
                elif platform == "x":
                    result = await _search_x(keyword, post_limit)
                else:
                    return platform, [], f"Unsupported platform: {platform}"

                if result.success:
                    return platform, result.posts, None
                else:
                    return platform, [], result.error_message or "Search returned no results"
            except Exception as e:
                logger.exception(f"Error searching {platform}")
                return platform, [], str(e)

        platform_tasks = [search_platform(p) for p in platforms]
        results = await asyncio.gather(*platform_tasks)

        # Collect posts and error log
        for platform, posts, error in results:
            if error:
                error_log[platform] = error
                logger.warning(f"Platform {platform} error: {error}")
            for post_data in posts:
                all_posts.append((platform, post_data))

        # Determine metrics_partial per platform
        platform_has_metrics = {}
        for platform, post_data in all_posts:
            if platform not in platform_has_metrics:
                has_any = any(
                    post_data.views > 0 or post_data.likes > 0 or
                    post_data.comments_count > 0 or post_data.shares > 0
                    for p2, post_data in all_posts if p2 == platform
                )
                platform_has_metrics[platform] = has_any

        # Insert SentimentPost rows
        sent_posts = []
        sort_idx = 0
        for platform, post_data in all_posts:
            metrics_partial = not platform_has_metrics.get(platform, False)
            sort_idx += 1
            sp = SentimentPost(
                task_id=task_id,
                platform=platform,
                post_id=post_data.url or f"unknown-{len(sent_posts)}",
                title=post_data.title or "",
                content=post_data.content or post_data.title or "",
                url=post_data.url or "",
                author_name=post_data.author_name or "",
                author_avatar=post_data.author_avatar or "",
                author_followers=post_data.author_followers or 0,
                published_at=post_data.published_at,
                views=post_data.views or 0,
                sort_order=sort_idx,
                likes=post_data.likes or 0,
                comments=post_data.comments_count or 0,
                shares=post_data.shares or 0,
                bookmarks=post_data.bookmarks or 0,
                images_json=json.dumps(post_data.images, ensure_ascii=False) if (post_data.images and platform != "xiaohongshu") else None,
                videos_json=json.dumps(post_data.videos, ensure_ascii=False) if (post_data.videos and platform != "xiaohongshu") else None,
                comments_json=json.dumps([{"text": c.text, "author": c.author, "likes": c.likes} for c in post_data.comments], ensure_ascii=False) if post_data.comments else None,
                quoted_tweet_json=json.dumps(post_data.quoted_tweet, ensure_ascii=False) if post_data.quoted_tweet else None,
                card_json=json.dumps(post_data.card, ensure_ascii=False) if post_data.card else None,
                metrics_partial=metrics_partial,
                fetched_at=datetime.utcnow(),
            )
            db.add(sp)
            sent_posts.append(sp)

        await db.flush()

        # Calculate scores
        for sp in sent_posts:
            score_result = calculate_impact(
                sp,
                stats_dict,
                PLATFORM_MAU_DEFAULTS,
                half_life_days=half_life_days,
                all_platform_values=all_values,
            )
            sp.engagement_score = score_result["engagement_score"]
            sp.platform_weight = score_result["platform_weight"]
            sp.time_decay = score_result["time_decay"]
            sp.impact_score = score_result["impact_score"]
            sp.score_detail = score_result["score_detail"]

        # Finalize task
        task.total_posts = len(sent_posts)
        task.error_log = json.dumps(error_log, ensure_ascii=False) if error_log else None
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        await db.commit()

        logger.info(
            f"SentimentTask {task_id} completed: "
            f"{len(sent_posts)} posts from {len(platforms)} platforms"
        )


async def _search_xiaohongshu(keyword: str, limit: int):
    """Search Xiaohongshu via CDP browser driver (Chrome login required)."""
    from crawlers.xhs_cdp_search import search_xhs
    return await search_xhs(keyword, limit)


async def _search_toutiao(keyword: str, limit: int):
    """Search Toutiao: try CDP first (reuses Chrome login), fall back to Scrapling."""
    try:
        crawler = ToutiaoCrawler()
        result = await crawler.search_by_keyword(keyword, limit=limit)
        if result.success:
            return result
        logger.warning(f"Toutiao CDP failed: {result.error_message}, trying Scrapling fallback...")
    except Exception as e:
        logger.warning(f"Toutiao CDP error: {e}, trying Scrapling fallback...")

    try:
        scrapling = ToutiaoScraplingCrawler()
        return await scrapling.search_by_keyword(keyword, limit=limit)
    except Exception as e:
        logger.exception("Toutiao Scrapling search error")
        from crawlers.base import CrawlResult
        return CrawlResult(success=False, error_message=str(e))


async def _generate_youtube_summaries(posts: list):
    """Generate Chinese first-level summaries for YouTube videos via LLM.

    Called concurrently for each video post-data. Summaries are appended to
    ``PostData.content`` with a separator.
    """
    from services.summarizer import summarizer

    async def _summarize_one(p):
        if not p.title and not p.content:
            return
        try:
            system_prompt = (
                "你是一个视频内容摘要助手。请基于视频的标题和描述，生成一段简洁的中文摘要"
                "（100字以内），概括视频的核心内容。"
                "直接输出摘要文本，不要输出思考过程。"
            )
            user_prompt = f"标题：{p.title}\n描述：{(p.content or '')[:800]}"
            summary = await summarizer._call_ai(system_prompt, user_prompt)
            if summary:
                p.content = (p.content or "") + "\n\n【AI 摘要】\n" + summary.strip()
                logger.info(f"Youtube summary generated for: {p.title[:50]}")
        except Exception as e:
            logger.warning(f"Youtube summary failed for '{p.title[:50]}': {e}")

    tasks = [_summarize_one(p) for p in posts]
    await asyncio.gather(*tasks)


async def _search_x(keyword: str, limit: int):
    """Search X/Twitter: try OpenCLI first (reuses Chrome login), fall back to Playwright."""
    try:
        result = await search_x_via_opencli(keyword, limit=limit)
        if result.success:
            logger.info(f"X OpenCLI search returned {len(result.posts)} posts")
            # Fetch comments for each post
            await _fetch_x_comments_for_posts(result.posts)
            return result
        logger.warning(f"X OpenCLI search failed: {result.error_message}, trying Playwright fallback...")
    except Exception as e:
        logger.warning(f"X OpenCLI error: {e}, trying Playwright fallback...")

    try:
        from crawlers.x_search_playwright import search_x_via_playwright
        result = await search_x_via_playwright(keyword, limit=limit)
        if result.success:
            logger.info(f"X Playwright search returned {len(result.posts)} posts")
            await _fetch_x_comments_for_posts(result.posts)
            return result
        logger.warning(f"X Playwright search also failed: {result.error_message}")
        return result
    except ImportError:
        logger.error("x_search_playwright module not found")
        from crawlers.base import CrawlResult
        return CrawlResult(success=False, error_message="X search not available (module missing)")
    except Exception as e:
        logger.exception("X Playwright search error")
        from crawlers.base import CrawlResult
        return CrawlResult(success=False, error_message=str(e))


async def _fetch_x_comments_for_posts(posts: list, max_comments_per_post: int = 5):
    """Fetch top comments for X posts via opencli twitter thread command."""
    import subprocess as _sp

    if not posts:
        return

    opencli_path = shutil.which("opencli")
    if not opencli_path:
        logger.warning("opencli not found, cannot fetch X comments")
        return

    from crawlers.base import CommentData

    for post in posts:
        try:
            tweet_id = _extract_tweet_id_from_url(post.url)
            if not tweet_id:
                continue

            # Call opencli twitter thread to get conversation (original + replies)
            args = ["twitter", "thread", tweet_id, "--limit", "20", "--format", "json"]

            stdout = await asyncio.to_thread(
                lambda: _sp.run(
                    [opencli_path] + args,
                    capture_output=True,
                    timeout=45,
                )
            )
            raw = stdout.stdout.decode("utf-8", errors="ignore").strip()

            # Extract JSON array
            start = raw.find("[")
            start2 = raw.find("{")
            if start < 0 or (start2 >= 0 and start2 < start):
                start = start2
            if start >= 0:
                raw = raw[start:]

            data = json.loads(raw) if raw else None
            if not data:
                continue

            items = data if isinstance(data, list) else [data]
            comments = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id", "")
                if item_id == tweet_id:
                    continue  # Skip the original tweet
                text = item.get("text", "")
                if not text:
                    continue
                author = item.get("author", "")
                likes = int(item.get("likes", 0) or 0)
                comments.append(CommentData(text=text, author=author, likes=likes))

            comments.sort(key=lambda c: c.likes, reverse=True)
            comments = comments[:max_comments_per_post]
            if comments:
                post.comments = comments
                logger.info(f"X: fetched {len(comments)} comments for tweet {tweet_id}")

            # Rate limit between requests
            await asyncio.sleep(1)

        except Exception as e:
            logger.warning(f"X comment fetch error for {post.url}: {e}")
            continue


def _extract_tweet_id_from_url(url: str) -> str | None:
    """Extract tweet ID from X URL like https://x.com/user/status/1234567890"""
    import re
    if not url:
        return None
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None


def _parse_tweet_detail_comments(data: dict, own_tweet_id: str, max_comments: int = 5) -> list:
    """Parse TweetDetail response to extract top-level replies (comments)."""
    from crawlers.base import CommentData

    instructions = (
        data.get("data", {})
        .get("threaded_conversation_with_injections_v2", {})
        .get("instructions", [])
    )

    replies = []
    for inst in instructions:
        for entry in inst.get("entries", []):
            content = entry.get("content", {})
            items = content.get("items", [])
            for item in items:
                tweet_result = (
                    item.get("item", {})
                    .get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                # Unwrap TweetWithVisibilityResults
                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", {}) or {}
                if not tweet_result:
                    continue

                rest_id = tweet_result.get("rest_id", "")
                # Skip own tweet
                if rest_id == own_tweet_id:
                    continue

                legacy = tweet_result.get("legacy", {})
                if not legacy:
                    continue

                text = legacy.get("full_text", "")
                if not text:
                    continue

                user_result = (
                    tweet_result.get("core", {})
                    .get("user_results", {})
                    .get("result", {})
                )
                author = user_result.get("legacy", {}).get("screen_name", "")
                likes = legacy.get("favorite_count", 0)

                replies.append(CommentData(text=text, author=author, likes=likes))

    # Sort by likes descending, take top N
    replies.sort(key=lambda c: c.likes, reverse=True)
    return replies[:max_comments]


async def _get_x_ct0() -> str | None:
    """Get X ct0 cookie from Chrome via CDP or Playwright persistent profile."""
    import httpx
    from playwright.async_api import async_playwright

    # 1. Try to detect Chrome CDP port (OpenCLI uses it)
    cdp_port = None
    for port in [9222, 9223, 9224, 9225, 9226]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"http://localhost:{port}/json/version")
                if resp.status_code == 200:
                    cdp_port = port
                    break
        except Exception:
            continue

    if cdp_port:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
                contexts = browser.contexts
                for ctx in contexts:
                    cookies = await ctx.cookies("https://x.com")
                    for c in cookies:
                        if c.get("name") == "ct0" and c.get("value"):
                            return c.get("value")
        except Exception as e:
            logger.warning(f"Failed to get X ct0 via CDP: {e}")

    # 2. Fallback: Playwright persistent profile
    try:
        from pathlib import Path

        user_data_dir = Path("backend/data/x_profile")
        if not user_data_dir.exists():
            return None

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                cookies = await context.cookies("https://x.com")
                for cookie in cookies:
                    if cookie.get("name") == "ct0":
                        return cookie.get("value")
                # Also try navigating to x.com to refresh
                page = await context.new_page()
                await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=10000)
                cookies = await context.cookies("https://x.com")
                for cookie in cookies:
                    if cookie.get("name") == "ct0":
                        return cookie.get("value")
            finally:
                await context.close()
    except Exception as e:
        logger.warning(f"Failed to get X ct0 cookie from persistent profile: {e}")

    return None
