# intel-monitor/backend/services/monitor.py
import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from models.comment import HotComment
from crawlers import CRAWLER_MAP, WebsiteCrawler, get_router
from crawlers.base import filter_posts, _run_crawler_in_thread
from services.summarizer import summarizer

logger = logging.getLogger(__name__)


async def crawl_with_fallback(
    platform: str,
    account_name: str,
    account_url: str,
    post_limit: int = 10,
    post_time_range_days: int = 0,
) -> tuple:
    """Try crawlers in priority order via CrawlerRouter.
    Returns (CrawlResult, method_name, error_log).
    """
    router = get_router()
    result, method, error_log = await router.crawl(platform, account_name, account_url, post_limit)

    if result and result.success:
        result.posts = filter_posts(result.posts, post_limit, post_time_range_days)
        img_total = sum(len(p.images) for p in result.posts)
        logger.info(f"[{account_name}] {method} 成功: {len(result.posts)} 条, {img_total} 张图片")

    return result, method, error_log


async def _mark_pending_as_failed(db: AsyncSession, target_id: int, target_type: str):
    """Mark any pending result for this target as failed (e.g. when target doesn't exist)."""
    result = await db.execute(
        select(MonitorResult).where(
            MonitorResult.target_id == target_id,
            MonitorResult.target_type == target_type,
            MonitorResult.status == "pending",
        ).order_by(MonitorResult.id.desc()).limit(1)
    )
    pending = result.scalars().first()
    if pending:
        pending.status = "failed"
        pending.error_message = f"Target (id={target_id}) not found"
        await db.commit()


async def execute_monitor(target_id: int, target_type: str = "social_media"):
    """Execute monitoring for a single target."""
    async with async_session() as db:
        if target_type == "social_media":
            result = await db.execute(select(Target).where(Target.id == target_id))
            target = result.scalar_one_or_none()
            if not target:
                await _mark_pending_as_failed(db, target_id, target_type)
                return
            await _monitor_social_target(db, target)
        else:
            result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.id == target_id))
            target = result.scalar_one_or_none()
            if not target:
                await _mark_pending_as_failed(db, target_id, target_type)
                return
            await _monitor_website_target(db, target)


async def _monitor_social_target(db: AsyncSession, target: Target):
    logger.info(f"=== 开始监控: {target.account_name} (平台: {target.platform}, ID: {target.id}) ===")

    # Check for an existing pending result (created by run_now endpoint)
    result = await db.execute(
        select(MonitorResult).where(
            MonitorResult.target_id == target.id,
            MonitorResult.target_type == "social_media",
            MonitorResult.monitor_date == date.today(),
            MonitorResult.status == "pending",
        ).order_by(MonitorResult.id.desc()).limit(1)
    )
    monitor_result = result.scalars().first()

    if not monitor_result:
        monitor_result = MonitorResult(
            target_id=target.id,
            target_type="social_media",
            monitor_date=date.today(),
            status="pending",
        )
        db.add(monitor_result)
        await db.commit()
        await db.refresh(monitor_result)

    try:
        crawl_result, method, error_log = await crawl_with_fallback(
            platform=target.platform,
            account_name=target.account_name,
            account_url=target.account_url,
            post_limit=getattr(target, 'post_limit', 10),
            post_time_range_days=getattr(target, 'post_time_range_days', 0),
        )

        monitor_result.crawl_method = method

        if not crawl_result or not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = " | ".join(error_log) if error_log else (crawl_result.error_message if crawl_result else "所有爬取方式均失败")
            logger.error(f"[{target.account_name}] 所有爬虫失败: {monitor_result.error_message}")
            await db.commit()
            return

        all_comments = []
        # 仅 Playwright 方式尝试获取评论（CDP 和 OpenCLI 暂不支持评论回填）
        if method == "playwright":
            crawler_cls = CRAWLER_MAP.get(target.platform)
            if crawler_cls:
                playwright_crawler = crawler_cls()
                for post in crawl_result.posts:
                    if post.url:
                        try:
                            comments = await _run_crawler_in_thread(playwright_crawler.get_hot_comments(post.url))
                            post.comments = comments
                            all_comments.extend(comments)
                        except Exception:
                            pass

        # 图片提取统计
        img_count = sum(len(p.images) for p in crawl_result.posts)
        posts_with_images = sum(1 for p in crawl_result.posts if p.images)
        logger.info(f"[{target.account_name}] 爬取完成: {len(crawl_result.posts)} 条帖子, {posts_with_images} 条含图片, 共 {img_count} 张图片 (方法: {method})")
        if img_count > 0:
            sample_urls = [img for p in crawl_result.posts[:2] for img in p.images[:1]]
            logger.info(f"[{target.account_name}] 图片示例: {sample_urls}")

        # Summarize
        logger.info(f"[{target.account_name}] 开始生成摘要{'(含图片分析)' if img_count > 0 else ''}")
        summary = await summarizer.summarize_posts(target.platform, target.account_name, crawl_result.posts)
        hot = await summarizer.extract_hot_comments(all_comments)
        logger.info(f"[{target.account_name}] 摘要完成, 长度: {len(summary)} 字符")

        # Save results
        monitor_result.summary = summary
        monitor_result.raw_content = json.dumps(
            [{"title": p.title, "content": p.content, "url": p.url, "likes": p.likes, "images": p.images, "author_name": p.author_name, "author_avatar": p.author_avatar, "published_at": p.published_at.isoformat() if p.published_at else None} for p in crawl_result.posts],
            ensure_ascii=False,
        )
        monitor_result.status = "success"

        # Save hot comments
        for i, comment in enumerate(hot):
            db.add(HotComment(
                monitor_result_id=monitor_result.id,
                post_url=comment.url,
                comment_text=comment.text,
                author=comment.author,
                likes_count=comment.likes,
                rank=i + 1,
            ))

        await db.commit()
        logger.info(f"[{target.account_name}] === 监控完成 (结果ID: {monitor_result.id}) ===")

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        logger.exception(f"[{target.account_name}] 监控异常")
        await db.commit()


async def _monitor_website_target(db: AsyncSession, target: WebsiteTarget):
    # Check for an existing pending result (created by run_now endpoint)
    result = await db.execute(
        select(MonitorResult).where(
            MonitorResult.target_id == target.id,
            MonitorResult.target_type == "website",
            MonitorResult.monitor_date == date.today(),
            MonitorResult.status == "pending",
        ).order_by(MonitorResult.id.desc()).limit(1)
    )
    monitor_result = result.scalars().first()

    if not monitor_result:
        monitor_result = MonitorResult(
            target_id=target.id,
            target_type="website",
            monitor_date=date.today(),
            status="pending",
        )
        db.add(monitor_result)
        await db.commit()
        await db.refresh(monitor_result)

    try:
        crawler = WebsiteCrawler()
        crawl_result = await _run_crawler_in_thread(crawler.crawl(target.url, target.css_selector))

        if not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = crawl_result.error_message
            await db.commit()
            return

        content = crawl_result.posts[0].content if crawl_result.posts else ""
        summary = await summarizer.summarize_website(target.name, content)

        monitor_result.summary = summary
        monitor_result.raw_content = content[:10000]
        monitor_result.crawl_method = "playwright"
        monitor_result.status = "success"
        await db.commit()

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        await db.commit()


async def monitor_all_active():
    """Run monitoring for all active targets (called by scheduler)."""
    async with async_session() as db:
        # Social media targets
        result = await db.execute(select(Target).where(Target.is_active == True))
        targets = result.scalars().all()
        for target in targets:
            try:
                await execute_monitor(target.id, "social_media")
            except Exception:
                pass

        # Website targets
        result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.is_active == True))
        websites = result.scalars().all()
        for website in websites:
            try:
                await execute_monitor(website.id, "website")
            except Exception:
                pass
