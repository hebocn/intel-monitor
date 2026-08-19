# intel-monitor/backend/services/monitor.py
import asyncio
import json
import logging
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from models.comment import HotComment
from crawlers import CRAWLER_MAP, WebsiteCrawler, OpenCLICrawler, get_router
from crawlers.base import filter_posts, _run_crawler_in_thread
from services.summarizer import summarizer
from services.feishu import push_monitor_result

logger = logging.getLogger(__name__)


async def crawl_with_fallback(
    platform: str,
    account_name: str,
    account_url: str,
    post_limit: int = 10,
    post_time_range_days: int = 0,
    time_start=None,
    time_end=None,
) -> tuple:
    """Try crawlers in priority order via CrawlerRouter.
    Returns (CrawlResult, method_name, error_log).

    time_start/time_end: 绝对时间窗口（naive UTC datetime）。"立即执行"时由前端传入；
    指定后放宽抓取条数（各平台爬虫自行封顶），保证有足够候选帖子供时间筛选。
    """
    router = get_router()

    has_window = time_start is not None or time_end is not None
    fetch_limit = max(post_limit, 100) if has_window else post_limit
    result, method, error_log = await router.crawl(platform, account_name, account_url, fetch_limit)

    if result and result.success:
        # 时间窗口模式下返回窗口内全部匹配帖子（上限 200），不受目标 post_limit 截断
        result_limit = max(post_limit, 200) if has_window else post_limit
        result.posts = filter_posts(result.posts, result_limit, post_time_range_days, time_start, time_end)
        img_total = sum(len(p.images) for p in result.posts)
        logger.info(f"[{account_name}] {method} 成功: {len(result.posts)} 条, {img_total} 张图片"
                    + (" (时间窗口筛选)" if has_window else ""))

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


async def execute_monitor(target_id: int, target_type: str = "social_media", time_start=None, time_end=None):
    """Execute monitoring for a single target.

    time_start/time_end: 绝对时间窗口（naive UTC），"立即执行"时由前端传入；
    仅社交账号监测生效，调度任务不传（沿用目标相对时间配置）。
    """
    async with async_session() as db:
        if target_type == "social_media":
            result = await db.execute(select(Target).where(Target.id == target_id))
            target = result.scalar_one_or_none()
            if not target:
                await _mark_pending_as_failed(db, target_id, target_type)
                return
            await _monitor_social_target(db, target, time_start=time_start, time_end=time_end)
        else:
            result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.id == target_id))
            target = result.scalar_one_or_none()
            if not target:
                await _mark_pending_as_failed(db, target_id, target_type)
                return
            await _monitor_website_target(db, target)


async def _monitor_social_target(db: AsyncSession, target: Target, time_start=None, time_end=None):
    if time_start is not None or time_end is not None:
        logger.info(
            f"=== 开始监控: {target.account_name} (平台: {target.platform}, ID: {target.id}, "
            f"时间窗口: {time_start} ~ {time_end}) ==="
        )
    else:
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
            time_start=time_start,
            time_end=time_end,
        )

        monitor_result.crawl_method = method

        if not crawl_result or not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = " | ".join(error_log) if error_log else (crawl_result.error_message if crawl_result else "所有爬取方式均失败")
            logger.error(f"[{target.account_name}] 所有爬虫失败: {monitor_result.error_message}")
            await db.commit()
            await push_monitor_result("social_media", target.id)
            return

        # 评论改为按需获取：监控只抓帖子，用户在前端逐帖点击「获取评论」后才抓取并入库

        # 图片提取统计
        img_count = sum(len(p.images) for p in crawl_result.posts)
        posts_with_images = sum(1 for p in crawl_result.posts if p.images)
        logger.info(f"[{target.account_name}] 爬取完成: {len(crawl_result.posts)} 条帖子, {posts_with_images} 条含图片, 共 {img_count} 张图片 (方法: {method})")
        if img_count > 0:
            sample_urls = [img for p in crawl_result.posts[:2] for img in p.images[:1]]
            logger.info(f"[{target.account_name}] 图片示例: {sample_urls}")

        # Summarize
        if crawl_result.posts:
            logger.info(f"[{target.account_name}] 开始生成摘要{'(含图片分析)' if img_count > 0 else ''}")
            summary = await summarizer.summarize_posts(target.platform, target.account_name, crawl_result.posts)
            logger.info(f"[{target.account_name}] 摘要完成, 长度: {len(summary)} 字符")
        else:
            summary = "所选时间范围内无贴文。" if (time_start is not None or time_end is not None) else "今日无新内容发布。"
            logger.info(f"[{target.account_name}] 时间筛选后无贴文, 跳过摘要")

        # Save results
        monitor_result.summary = summary
        monitor_result.raw_content = json.dumps(
            [{"title": p.title, "content": p.content, "url": p.url, "likes": p.likes, "comments_count": p.comments_count, "images": p.images, "author_name": p.author_name, "author_avatar": p.author_avatar, "published_at": p.published_at.isoformat() if p.published_at else None} for p in crawl_result.posts],
            ensure_ascii=False,
        )
        monitor_result.status = "success"
        await db.commit()
        await push_monitor_result("social_media", target.id, time_start, time_end)
        logger.info(f"[{target.account_name}] === 监控完成 (结果ID: {monitor_result.id}) ===")

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        logger.exception(f"[{target.account_name}] 监控异常")
        await db.commit()
        await push_monitor_result("social_media", target.id)


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
        crawl_result = await _run_crawler_in_thread(
            crawler.crawl(target.url, target.css_selector), timeout=180)

        if not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = crawl_result.error_message
            await db.commit()
            await push_monitor_result("website", target.id)
            return

        content = crawl_result.posts[0].content if crawl_result.posts else ""
        images = crawl_result.posts[0].images if crawl_result.posts else []
        summary = await summarizer.summarize_website(target.name, content, images=images)

        monitor_result.summary = summary
        monitor_result.raw_content = content[:10000]
        monitor_result.crawl_method = crawl_result.method or "unknown"
        monitor_result.status = "success"
        await db.commit()
        await push_monitor_result("website", target.id)

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        await db.commit()
        await push_monitor_result("website", target.id)


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


async def fetch_post_comments(monitor_result_id: int, post_url: str) -> dict:
    """Fetch hot comments for a single post (on-demand) and store them.

    Returns {"comments": N, "rank": 1} where rank is the in-post rank of the
    top comment (0 if none). Errors raise HTTPException with detail message.
    """
    async with async_session() as db:
        result = await db.execute(select(MonitorResult).where(MonitorResult.id == monitor_result_id))
        monitor_result = result.scalar_one_or_none()
        if not monitor_result:
            raise HTTPException(status_code=404, detail="结果不存在")

        target_result = await db.execute(select(Target).where(Target.id == monitor_result.target_id))
        target = target_result.scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="监控目标不存在")

        crawler_cls = CRAWLER_MAP.get(target.platform)
        if not crawler_cls:
            raise HTTPException(status_code=400, detail=f"平台 {target.platform} 不支持评论获取")

        # 抓取前先标记精选中（idle -> selecting）
        monitor_result.comments_ai_status = "selecting"
        await db.commit()

        try:
            # X 平台通过 OpenCLI 复用登录态抓取评论（Playwright 无登录态会返回 0 条）
            if target.platform == "x":
                opencli_crawler = OpenCLICrawler(platform="x")
                comments = await opencli_crawler.get_hot_comments(post_url)
            else:
                crawler = crawler_cls()
                comments = await _run_crawler_in_thread(crawler.get_hot_comments(post_url))
        except Exception as e:
            monitor_result.comments_ai_status = "idle"
            await db.commit()
            logger.warning(f"[{target.account_name}] 评论抓取失败: {post_url[-30:]} ({e})")
            raise HTTPException(status_code=500, detail=f"评论抓取失败: {e}")

        for c in comments:
            c.url = post_url

        # 覆盖写入：先删该帖旧评论，再写新评论（帖内 rank 1-10）
        await db.execute(
            delete(HotComment).where(
                HotComment.monitor_result_id == monitor_result.id,
                HotComment.post_url == post_url,
            )
        )
        for i, c in enumerate(comments[:10]):
            db.add(HotComment(
                monitor_result_id=monitor_result.id,
                post_url=post_url,
                comment_text=c.text,
                author=c.author,
                likes_count=c.likes,
                reply_count=c.reply_count,
                retweet_count=c.retweet_count,
                rank=i + 1,
            ))
        await db.commit()
        logger.info(f"[{target.account_name}] 按需评论: {post_url[-20:]} -> {len(comments)} 条 (结果ID: {monitor_result.id})")

        # 触发异步 AI 精选全局 TOP10（后台任务，不阻塞响应）
        asyncio.create_task(select_global_hot_comments(monitor_result.id))
        return {"comments": len(comments), "rank": 1 if comments else 0}


async def _reset_global_ranks(db, monitor_result_id: int):
    """清空该结果所有评论的全局排名（精选重算前调用）。"""
    from sqlalchemy import update
    await db.execute(
        update(HotComment)
        .where(HotComment.monitor_result_id == monitor_result_id)
        .values(global_rank=0)
    )
    await db.commit()


async def select_global_hot_comments(monitor_result_id: int):
    """Select global TOP10 hot comments from all stored comments via AI (background)."""
    async with async_session() as db:
        result = await db.execute(
            select(MonitorResult)
            .options(selectinload(MonitorResult.hot_comments))
            .where(MonitorResult.id == monitor_result_id)
        )
        monitor_result = result.scalar_one_or_none()
        if not monitor_result:
            return
        try:
            await _reset_global_ranks(db, monitor_result.id)
            all_comments = monitor_result.hot_comments
            if not all_comments:
                monitor_result.comments_ai_status = "idle"
                await db.commit()
                return
            # 按帖分组取每帖热度 TOP3 作为候选（防单帖霸榜）
            by_post: dict[str, list] = {}
            for c in all_comments:
                by_post.setdefault(c.post_url, []).append(c)
            def _heat(c):
                return c.likes_count + max(c.reply_count, c.retweet_count) * 2
            truncated = []
            for post_comments in by_post.values():
                post_comments.sort(key=_heat, reverse=True)
                truncated.extend(post_comments[:3])
            sorted_comments = sorted(truncated, key=_heat, reverse=True)
            candidates = sorted_comments[:20]

            if len(candidates) <= 10:
                for i, c in enumerate(sorted_comments[:10]):
                    c.global_rank = i + 1
                monitor_result.comments_ai_status = "done"
                await db.commit()
                return

            def _fmt(c):
                extra = ""
                if c.reply_count: extra = f",{c.reply_count}回复"
                elif c.retweet_count: extra = f",{c.retweet_count}转发"
                return f"[{c.likes_count}赞{extra}] {c.author}: {c.comment_text[:100]}"
            comments_text = "\n".join(f"{i+1}. {_fmt(c)}" for i, c in enumerate(candidates))
            system_prompt = (
                "从以下评论中选出最有价值、最热门的10条。"
                "按热度排序，返回编号列表，每行一个编号。"
                "只返回编号，如: 1,3,5,7,9,11,13,15,17,19"
            )
            result = await summarizer._call_ai(system_prompt, comments_text)
            indices = [int(x.strip()) - 1 for x in result.replace("\n", ",").split(",") if x.strip().isdigit()]
            chosen = [candidates[i] for i in indices if 0 <= i < len(candidates)][:10]
            if not chosen:
                chosen = sorted_comments[:10]
            # 写全局 rank 1-10（帖内 rank 保留）
            for i, c in enumerate(chosen):
                c.global_rank = i + 1
            monitor_result.comments_ai_status = "done"
            await db.commit()
            logger.info(f"[monitor] AI 精选全局 TOP10 完成: {len(chosen)} 条 (结果ID: {monitor_result.id})")
        except Exception as e:
            monitor_result.comments_ai_status = "idle"
            await db.commit()
            logger.exception(f"[monitor] AI 精选失败 (结果ID: {monitor_result.id}): {e}")
