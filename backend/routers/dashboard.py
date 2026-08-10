# intel-monitor/backend/routers/dashboard.py
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from models.sentiment_task import SentimentTask
from models.sentiment_post import SentimentPost
from models.intelligence_report import IntelligenceReport
from schemas.dashboard import (
    DashboardStats, RecentResultItem, DashboardResponse,
    TrendPoint, PlatformStat,
    SentimentSummary, IntelligenceSummary, SystemHealth,
    DashboardOverviewResponse,
)

BJT = timezone(timedelta(hours=8))


def utc_to_bjt(dt: datetime) -> datetime:
    """Convert naive UTC datetime to Beijing time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BJT)


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# platform label map
PLATFORM_LABELS: dict[str, str] = {
    "x": "X", "youtube": "YouTube", "xiaohongshu": "小红书",
    "douyin": "抖音", "weibo": "微博", "bilibili": "B站",
    "reddit": "Reddit", "toutiao": "头条", "website": "网站",
}


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ── Target counts ──
    target_count = (await db.execute(
        select(func.count()).select_from(Target).where(Target.user_id == user.id)
    )).scalar()
    active_count = (await db.execute(
        select(func.count()).select_from(Target).where(Target.user_id == user.id, Target.is_active == True)
    )).scalar()
    website_count = (await db.execute(
        select(func.count()).select_from(WebsiteTarget).where(WebsiteTarget.user_id == user.id)
    )).scalar()

    # ── Today's results ──
    today = date.today()
    today_total = (await db.execute(
        select(func.count()).select_from(MonitorResult).where(MonitorResult.monitor_date == today)
    )).scalar()
    today_success = (await db.execute(
        select(func.count()).select_from(MonitorResult).where(
            MonitorResult.monitor_date == today, MonitorResult.status == "success"
        )
    )).scalar()
    today_failed = (await db.execute(
        select(func.count()).select_from(MonitorResult).where(
            MonitorResult.monitor_date == today, MonitorResult.status == "failed"
        )
    )).scalar()

    # ── Crawl method stats (today) ──
    crawl_method_rows = (await db.execute(
        select(MonitorResult.crawl_method, func.count())
        .where(MonitorResult.monitor_date == today, MonitorResult.crawl_method.isnot(None))
        .group_by(MonitorResult.crawl_method)
    )).all()
    crawl_map: dict[str, int] = {row[0]: row[1] for row in crawl_method_rows if row[0]}

    # ── Platform stats (today) ──
    _social_ts = (await db.execute(select(Target))).scalars().all()
    _platform_lookup = {t.id: t.platform for t in _social_ts}

    raw_platform_rows = (await db.execute(
        select(MonitorResult).where(MonitorResult.monitor_date == today)
    )).scalars().all()
    platform_agg: dict[str, dict] = {}
    for r in raw_platform_rows:
        if r.target_type == "social_media":
            p = _platform_lookup.get(r.target_id, "unknown")
        else:
            p = "website"
        if p not in platform_agg:
            platform_agg[p] = {"count": 0, "success": 0, "failed": 0}
        platform_agg[p]["count"] += 1
        if r.status == "success":
            platform_agg[p]["success"] += 1
        elif r.status == "failed":
            platform_agg[p]["failed"] += 1

    platform_stats = []
    for p, agg in sorted(platform_agg.items(), key=lambda x: x[1]["count"], reverse=True):
        if agg["count"] > 0:
            agg["success_rate"] = round(agg["success"] / agg["count"] * 100, 1)
        else:
            agg["success_rate"] = 0.0
        platform_stats.append(PlatformStat(
            platform=p,
            label=PLATFORM_LABELS.get(p, p),
            count=agg["count"],
            success=agg["success"],
            failed=agg["failed"],
            success_rate=agg["success_rate"],
        ))

    # ── 7-day trend ──
    trend_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_total = (await db.execute(
            select(func.count()).select_from(MonitorResult).where(MonitorResult.monitor_date == d)
        )).scalar() or 0
        day_success = (await db.execute(
            select(func.count()).select_from(MonitorResult).where(
                MonitorResult.monitor_date == d, MonitorResult.status == "success"
            )
        )).scalar() or 0
        day_failed = (await db.execute(
            select(func.count()).select_from(MonitorResult).where(
                MonitorResult.monitor_date == d, MonitorResult.status == "failed"
            )
        )).scalar() or 0
        trend_data.append(TrendPoint(
            date=d.strftime("%m-%d"),
            total=day_total,
            success=day_success,
            failed=day_failed,
        ))

    # ── Recent results (last 20) ──
    recent_query = (
        select(MonitorResult)
        .order_by(MonitorResult.created_at.desc())
        .limit(20)
    )
    recent_results_raw = (await db.execute(recent_query)).scalars().all()

    social_targets = (await db.execute(select(Target))).scalars().all()
    website_targets = (await db.execute(select(WebsiteTarget))).scalars().all()
    social_map = {t.id: (t.account_name, t.account_url, t.platform) for t in social_targets}
    website_map = {t.id: (t.name, t.url) for t in website_targets}

    recent_results = []
    for r in recent_results_raw:
        if r.target_type == "social_media":
            target_name, target_url, platform = social_map.get(r.target_id, (f"目标 #{r.target_id}", None, "unknown"))
        else:
            target_name, target_url = website_map.get(r.target_id, (f"网站 #{r.target_id}", None))
            platform = "website"
        recent_results.append(RecentResultItem(
            id=r.id,
            target_name=target_name,
            target_url=target_url,
            platform=platform,
            target_type=r.target_type,
            status=r.status,
            summary=r.summary,
            raw_content=r.raw_content,
            monitor_date=str(r.monitor_date),
            created_at=utc_to_bjt(r.created_at).strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        ))

    return DashboardResponse(
        stats=DashboardStats(
            total_targets=target_count,
            active_targets=active_count,
            total_websites=website_count,
            today_results=today_total,
            today_success=today_success,
            today_failed=today_failed,
            crawl_method_opencli=crawl_map.get("opencli", 0),
            crawl_method_cdp=crawl_map.get("cdp", 0),
            crawl_method_playwright=crawl_map.get("playwright", 0),
            crawl_method_scrapling=crawl_map.get("scrapling", 0),
            platforms_covered=len(platform_stats),
        ),
        recent_results=recent_results,
        trend_data=trend_data,
        platform_stats=platform_stats,
    )


# ══════════════════════════════════════════════════
# Dashboard Overview — 跨模块聚合摘要 (优化版)
# ══════════════════════════════════════════════════

@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ── Sentiment + Intelligence: 并行查询，分别 try/catch ──
    sentiment = SentimentSummary()
    intelligence = IntelligenceSummary()

    try:
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        # 3 条查询合并为 1 条聚合（single round-trip）
        stmt = (
            select(
                func.count(SentimentTask.id).label("total_tasks"),
                func.sum(
                    func.case((SentimentTask.created_at >= week_ago, 1), else_=0)
                ).label("this_week_tasks"),
            )
            .where(SentimentTask.user_id == user.id)
        )
        sent_result = (await db.execute(stmt)).one_or_none()
        sentiment.total_tasks = sent_result.total_tasks or 0
        sentiment.this_week_tasks = sent_result.this_week_tasks or 0

        # posts COUNT 单独查（跨用户，不筛选 user_id）
        sentiment.total_posts = (
            await db.execute(select(func.count()).select_from(SentimentPost))
        ).scalar() or 0
    except Exception:
        pass

    try:
        # intelligence: 1 条聚合查 total + in_progress + completed
        intel_stmt = (
            select(
                func.count(IntelligenceReport.id).label("total"),
                func.sum(
                    func.case(
                        (IntelligenceReport.status.in_(
                            ["pending", "searching", "analyzing", "scraping", "writing"]
                        ), 1),
                        else_=0,
                    )
                ).label("in_progress"),
                func.sum(
                    func.case((IntelligenceReport.status == "completed", 1), else_=0)
                ).label("completed"),
            )
            .where(IntelligenceReport.user_id == user.id)
        )
        intel_result = (await db.execute(intel_stmt)).one_or_none()
        intelligence.total_reports = intel_result.total or 0
        intelligence.in_progress = intel_result.in_progress or 0
        intelligence.completed = intel_result.completed or 0
    except Exception:
        pass

    # ── System health: AI provider from config (快), 网络检查延迟副线程 ──
    system_health = SystemHealth()
    try:
        from config import settings
        system_health.ai_provider = settings.AI_PROVIDER or ""
        import os
        if settings.AI_PROVIDER == "minimax":
            system_health.ai_model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
        elif settings.AI_PROVIDER == "deepseek":
            system_health.ai_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        elif settings.AI_PROVIDER == "mimo":
            system_health.ai_model = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
        else:
            system_health.ai_model = settings.AI_PROVIDER or ""
    except Exception:
        pass

    # ── System health (AI provider only — fast, no network I/O) ──
    system_health = SystemHealth()
    try:
        from config import settings
        system_health.ai_provider = settings.AI_PROVIDER or ""
        import os
        if settings.AI_PROVIDER == "minimax":
            system_health.ai_model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
        elif settings.AI_PROVIDER == "deepseek":
            system_health.ai_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        elif settings.AI_PROVIDER == "mimo":
            system_health.ai_model = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
        else:
            system_health.ai_model = settings.AI_PROVIDER or ""
    except Exception:
        pass

    # OpenCLI/CDP 健康检查不在此端点执行——它们的 TCP connect 超时至少 0.5s，
    # 两个并行也要 0.5s+。改为前端调用专用端点懒加载。
    # 前端在 SystemHealthPanel 渲染后异步 fetch /api/tools/opencli-status 和
    # /api/tools/cdp-status 分步填充。

    return DashboardOverviewResponse(
        sentiment=sentiment,
        intelligence=intelligence,
        system_health=system_health,
    )


# ══════════════════════════════════════════════════
# 系统健康（网络依赖）— 独立端点，前端懒加载
# ══════════════════════════════════════════════════

@router.get("/health")
async def get_dashboard_health():
    """返回依赖网络的健康状态。前端在首页主数据加载完毕后异步调用。"""
    import asyncio, shutil, os

    result = {
        "opencli_installed": False,
        "opencli_running": False,
        "cdp_connected": False,
        "ai_provider": "",
        "ai_model": "",
    }

    try:
        from config import settings
        result["ai_provider"] = settings.AI_PROVIDER or ""
        if settings.AI_PROVIDER == "minimax":
            result["ai_model"] = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
        elif settings.AI_PROVIDER == "deepseek":
            result["ai_model"] = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        elif settings.AI_PROVIDER == "mimo":
            result["ai_model"] = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
    except Exception:
        pass

    async def check_opencli():
        if not shutil.which("opencli"):
            return
        result["opencli_installed"] = True
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.5, read=0.3, write=0.3, pool=0.3)) as client:
                r = await client.get("http://localhost:19825/status")
                result["opencli_running"] = r.status_code == 200
        except Exception:
            pass

    async def check_cdp():
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.5, read=0.3, write=0.3, pool=0.3)) as client:
                r = await client.get("http://localhost:3456/health")
                if r.status_code == 200:
                    data = r.json()
                    result["cdp_connected"] = data.get("connected", False)
        except Exception:
            pass

    await asyncio.gather(check_opencli(), check_cdp())

    return result
