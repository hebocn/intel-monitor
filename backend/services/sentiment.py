# intel-monitor/backend/services/sentiment.py
import asyncio
import json
import logging
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
        for platform, post_data in all_posts:
            metrics_partial = not platform_has_metrics.get(platform, False)
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
                likes=post_data.likes or 0,
                comments=post_data.comments_count or 0,
                shares=post_data.shares or 0,
                bookmarks=post_data.bookmarks or 0,
                images_json=json.dumps(post_data.images, ensure_ascii=False) if (post_data.images and platform != "xiaohongshu") else None,
                videos_json=json.dumps(post_data.videos, ensure_ascii=False) if (post_data.videos and platform != "xiaohongshu") else None,
                comments_json=json.dumps([{"text": c.text, "author": c.author, "likes": c.likes} for c in post_data.comments], ensure_ascii=False) if post_data.comments else None,
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
