# intel-monitor/backend/routers/dashboard.py
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from schemas.dashboard import DashboardStats, RecentResultItem, DashboardResponse

BJT = timezone(timedelta(hours=8))


def utc_to_bjt(dt: datetime) -> datetime:
    """Convert naive UTC datetime to Beijing time."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BJT)


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Target counts
    target_count = (await db.execute(
        select(func.count()).select_from(Target).where(Target.user_id == user.id)
    )).scalar()
    active_count = (await db.execute(
        select(func.count()).select_from(Target).where(Target.user_id == user.id, Target.is_active == True)
    )).scalar()
    website_count = (await db.execute(
        select(func.count()).select_from(WebsiteTarget).where(WebsiteTarget.user_id == user.id)
    )).scalar()

    # Today's results
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

    # Recent results (last 20) - join with targets to get names
    recent_query = (
        select(MonitorResult)
        .order_by(MonitorResult.created_at.desc())
        .limit(20)
    )
    recent_results_raw = (await db.execute(recent_query)).scalars().all()

    # Pre-fetch target info
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
        ),
        recent_results=recent_results,
    )
