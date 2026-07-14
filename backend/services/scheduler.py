import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from models.hot_topic_source import HotTopicSource
from services.monitor import execute_monitor
from sqlalchemy import select, delete

logger = logging.getLogger(__name__)

BJT = timezone(timedelta(hours=8))

scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Initialize the scheduler."""
    if not scheduler.running:
        scheduler.start()


def _parse_cron_trigger(expr: str) -> CronTrigger | None:
    """Parse a 5-field cron expression into a CronTrigger."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return None
    try:
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    except Exception:
        return None


async def refresh_jobs():
    """Reload all monitor jobs from database."""
    scheduler.remove_all_jobs()

    async with async_session() as db:
        # Social media targets
        result = await db.execute(select(Target).where(Target.is_active == True))
        targets = result.scalars().all()
        for t in targets:
            if t.cron_schedule:
                exprs = [e.strip() for e in t.cron_schedule.split(';') if e.strip()]
                for idx, expr in enumerate(exprs):
                    trigger = _parse_cron_trigger(expr)
                    if trigger:
                        scheduler.add_job(
                            execute_monitor,
                            trigger=trigger,
                            args=[t.id, "social_media"],
                            id=f"target_{t.id}_{idx}",
                            replace_existing=True,
                        )
                    else:
                        logger.warning(f"Invalid cron expression for target {t.id}: {expr}")
            else:
                scheduler.add_job(
                    execute_monitor,
                    trigger=CronTrigger(hour=t.monitor_hour, minute=t.monitor_minute),
                    args=[t.id, "social_media"],
                    id=f"target_{t.id}",
                    replace_existing=True,
                )

        # Website targets
        result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.is_active == True))
        websites = result.scalars().all()
        for w in websites:
            if w.cron_schedule:
                exprs = [e.strip() for e in w.cron_schedule.split(';') if e.strip()]
                for idx, expr in enumerate(exprs):
                    trigger = _parse_cron_trigger(expr)
                    if trigger:
                        scheduler.add_job(
                            execute_monitor,
                            trigger=trigger,
                            args=[w.id, "website"],
                            id=f"website_{w.id}_{idx}",
                            replace_existing=True,
                        )
                    else:
                        logger.warning(f"Invalid cron expression for website {w.id}: {expr}")
            else:
                scheduler.add_job(
                    execute_monitor,
                    trigger=CronTrigger(hour=w.monitor_hour, minute=w.monitor_minute),
                    args=[w.id, "website"],
                    id=f"website_{w.id}",
                    replace_existing=True,
                )

        # Hot topic sources
        from routers.hot_topics import execute_hot_topic_fetch
        result = await db.execute(
            select(HotTopicSource).where(HotTopicSource.is_active == True)
        )
        sources = result.scalars().all()
        for s in sources:
            if s.cron_schedule:
                exprs = [e.strip() for e in s.cron_schedule.split(';') if e.strip()]
                for idx, expr in enumerate(exprs):
                    trigger = _parse_cron_trigger(expr)
                    if trigger:
                        scheduler.add_job(
                            execute_hot_topic_fetch,
                            trigger=trigger,
                            args=[s.id],
                            id=f"hot_topic_{s.id}_{idx}",
                            replace_existing=True,
                        )
                    else:
                        logger.warning(f"Invalid cron expression for hot topic source {s.id}: {expr}")

        # PlatformStats daily refresh (3:07 AM BJT)
        scheduler.add_job(
            _refresh_platform_stats,
            trigger=CronTrigger(hour=3, minute=7),
            id="platform_stats_refresh",
            replace_existing=True,
        )

        # Sentiment cleanup (4:07 AM BJT, 30-day retention)
        scheduler.add_job(
            _cleanup_old_sentiment_tasks,
            trigger=CronTrigger(hour=4, minute=7),
            id="sentiment_cleanup",
            replace_existing=True,
        )


async def _refresh_platform_stats():
    """Daily task: recalculate percentile baselines."""
    from services.scoring import refresh_platform_stats
    try:
        await refresh_platform_stats()
    except Exception as e:
        logger.exception(f"PlatformStats refresh failed: {e}")


async def _cleanup_old_sentiment_tasks():
    """Delete sentiment tasks older than 30 days."""
    from models.sentiment_post import SentimentPost
    cutoff = datetime.utcnow() - timedelta(days=30)
    async with async_session() as db:
        old_tasks = await db.execute(
            select(SentimentTask.id).where(SentimentTask.created_at < cutoff)
        )
        task_ids = [r[0] for r in old_tasks.fetchall()]
        if task_ids:
            await db.execute(delete(SentimentPost).where(SentimentPost.task_id.in_(task_ids)))
            await db.execute(delete(SentimentTask).where(SentimentTask.id.in_(task_ids)))
            await db.commit()
            logger.info(f"Cleaned up {len(task_ids)} old sentiment tasks")


def get_job_status() -> list[dict]:
    """Get status of all scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run = None
        if job.next_run_time:
            dt = job.next_run_time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            next_run = dt.astimezone(BJT).strftime("%Y-%m-%d %H:%M:%S")
        jobs.append({
            "id": job.id,
            "next_run": next_run,
            "trigger": str(job.trigger),
        })
    return jobs
