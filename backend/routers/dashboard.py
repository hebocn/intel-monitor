# intel-monitor/backend/routers/dashboard.py
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text, case
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user, get_current_user_optional
from services.geo import GEO_CITY_MAP
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
    HotTopicPreview, SentimentSummary, IntelligenceSummary, SystemHealth,
    DashboardOverviewResponse,
    GeoSignal, GeoSignalsResponse,
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
    user: User | None = Depends(get_current_user_optional),
):
    # ── Target counts ──
    if user is not None:
        target_count = (await db.execute(
            select(func.count()).select_from(Target).where(Target.user_id == user.id)
        )).scalar()
        active_count = (await db.execute(
            select(func.count()).select_from(Target).where(Target.user_id == user.id, Target.is_active == True)
        )).scalar()
        website_count = (await db.execute(
            select(func.count()).select_from(WebsiteTarget).where(WebsiteTarget.user_id == user.id)
        )).scalar()
    else:
        # 未登录：返回全量计数
        target_count = (await db.execute(
            select(func.count()).select_from(Target)
        )).scalar()
        active_count = (await db.execute(
            select(func.count()).select_from(Target).where(Target.is_active == True)
        )).scalar()
        website_count = (await db.execute(
            select(func.count()).select_from(WebsiteTarget)
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
                    case((SentimentTask.created_at >= week_ago, 1), else_=0)
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
                    case(
                        (IntelligenceReport.status.in_(
                            ["pending", "searching", "analyzing", "scraping", "writing"]
                        ), 1),
                        else_=0,
                    )
                ).label("in_progress"),
                func.sum(
                    case((IntelligenceReport.status == "completed", 1), else_=0)
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

    # ── Hot Topics (仅微博, 去重 title, 最新 7 条) ──
    hot_topics: list[HotTopicPreview] = []
    try:
        from models.hot_topic import HotTopic
        ht_query = (
            select(HotTopic)
            .where(HotTopic.platform == "weibo")
            .order_by(HotTopic.fetched_at.desc().nullslast())
            .limit(50)
        )
        ht_raw = (await db.execute(ht_query)).scalars().all()
        seen: set[str] = set()
        for t in ht_raw:
            if t.title in seen:
                continue
            seen.add(t.title)
            hot_topics.append(HotTopicPreview(
                title=t.title,
                platform=t.platform,
                platform_label=PLATFORM_LABELS.get(t.platform, t.platform),
                hot_value=t.hot_value,
                rank=t.rank,
                url=t.url,
            ))
            if len(hot_topics) >= 7:
                break
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
        hot_topics=hot_topics,
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
                # OpenCLI daemon 对未认证 HTTP 请求返回 403（仅 CLI/扩展带认证），
                # 收到任何响应即说明 daemon 在运行。
                result["opencli_running"] = True
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


# ══════════════════════════════════════════════════
# Geo Signals — 世界地图情报标注
# ══════════════════════════════════════════════════

# GEO_CITY_MAP 已提取到 services/geo.py（dashboard 与 weather 共用）

PLATFORM_COLOR_MAP: dict[str, str] = {
    "x": "#1DA1F2", "youtube": "#FF0000", "xiaohongshu": "#FE2C55",
    "douyin": "#FFFFFF", "weibo": "#E6162D", "bilibili": "#00A1D6",
    "reddit": "#FF4500", "toutiao": "#E53333", "website": "#6495ED",
}

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Politics": ["政策", "政府", "选举", "白宫", "国会", "议会", "政治", "外交", "制裁", "联合国", "安理会",
                 "politics", "government", "election", "white house", "congress", "parliament",
                 "sanction", "united nations", "security council", "president"],
    "Economy": ["经济", "金融", "股市", "贸易", "GDP", "通胀", "利率", "央行", "人民币", "美元",
                "economy", "finance", "stock", "trade", "gdp", "inflation", "interest rate", "central bank"],
    "Tech": ["科技", "AI", "人工智能", "芯片", "半导体", "大模型", "量子", "5G", "特斯拉", "苹果",
             "tech", "ai", "artificial intelligence", "chip", "semiconductor", "quantum", "google", "apple", "tesla"],
    "Security": ["军事", "安全", "情报", "国防", "冲突", "战争", "武器", "导弹", "网络攻击",
                 "military", "security", "defense", "conflict", "war", "weapon", "missile", "cyber attack"],
    "Society": ["社会", "民生", "教育", "医疗", "环境", "气候", "能源", "灾害", "地震",
                "society", "education", "healthcare", "environment", "climate", "energy", "disaster", "earthquake"],
    "Culture": ["文化", "娱乐", "体育", "电影", "音乐", "艺术", "时尚",
                "culture", "entertainment", "sports", "movie", "music", "art", "fashion"],
}

CATEGORY_DEFAULT = "General"


def _extract_geo_signals(
    recent_results: list, hot_topics_raw: list
) -> tuple[list[GeoSignal], int, int, int]:
    """从监测结果和热门话题中提取带地理位置的情报信号。

    算法：遍历每条数据，在标题/摘要/内容中匹配城市关键词，
    按 (城市, 平台) 聚合计数，返回标注列表。
    """
    signals: dict[tuple[float, float, str], dict] = {}

    def _add_signal(lat: float, lng: float, name: str, platform: str,
                    platform_label: str, title: str, summary: str):
        key = (lat, lng, platform)
        if key in signals:
            signals[key]["count"] += 1
            # 保留最新的标题
            signals[key]["title"] = title
            signals[key]["summary"] = summary
        else:
            signals[key] = {
                "lat": lat, "lng": lng, "name": name,
                "platform": platform, "platform_label": platform_label,
                "color": PLATFORM_COLOR_MAP.get(platform, "#22C55E"),
                "title": title, "summary": summary, "count": 1,
            }

    def _classify(text: str) -> str:
        if not text:
            return CATEGORY_DEFAULT
        text_lower = text.lower()
        for cat, kws in CATEGORY_KEYWORDS.items():
            for kw in kws:
                if kw in text_lower:
                    return cat
        return CATEGORY_DEFAULT

    def _scan_text(text: str | None) -> list[tuple[float, float, str]]:
        """扫描文本，返回匹配到的所有城市名列表 (lat, lng, name)"""
        if not text:
            return []
        found: list[tuple[float, float, str]] = []
        for city_name, (lat, lng, en_name) in GEO_CITY_MAP.items():
            if city_name in text:
                found.append((lat, lng, city_name))
        return found

    # ── 1. 从近期监测结果中提取 ──
    for r in recent_results:
        platform = r.get("platform", "website")
        platform_label = PLATFORM_LABELS.get(platform, platform)
        target_name = r.get("target_name", "")
        summary_text = r.get("summary", "") or ""

        # 扫描 target_name + summary
        search_text = f"{target_name} {summary_text}"
        matches = _scan_text(search_text)

        # 如果没匹配到城市，跳过
        if not matches:
            continue

        # 从 raw_content 中找标题
        post_title = ""
        post_summary = ""
        raw = r.get("raw_content", "")
        if raw:
            try:
                import json
                posts = json.loads(raw)
                if isinstance(posts, list) and len(posts) > 0:
                    first_post = posts[0]
                    if isinstance(first_post, dict):
                        post_title = first_post.get("title", "") or first_post.get("content", "")[:100]
                        post_summary = summary_text[:200] if summary_text else ""
            except Exception:
                pass

        if not post_title:
            post_title = target_name

        category = _classify(f"{target_name} {summary_text}")

        for lat, lng, name in matches:
            _add_signal(lat, lng, name, platform, platform_label,
                        post_title, post_summary[:200])

    # ── 2. 从热门话题中提取 ──
    for topic in hot_topics_raw:
        title = topic.get("title", "")
        platform = topic.get("platform", "")
        platform_label = PLATFORM_LABELS.get(platform, platform)
        hot_value = topic.get("hot_value", "")

        matches = _scan_text(title)
        if not matches:
            continue

        category = _classify(title)
        summary = f"热度: {hot_value}" if hot_value else ""

        for lat, lng, name in matches:
            _add_signal(lat, lng, name, platform, platform_label,
                        title, summary)

    # ── 聚合去重（同一城市合并不同平台的 signal） ──
    result_signals: list[GeoSignal] = []
    regions: set[str] = set()
    platforms_set: set[str] = set()

    for key, sig in signals.items():
        _, _, platform = key
        result_signals.append(GeoSignal(
            name=sig.get("name", ""),
            lat=sig["lat"],
            lng=sig["lng"],
            platform=sig["platform"],
            platform_label=sig["platform_label"],
            color=sig["color"],
            category=_classify(f"{sig['title']} {sig['summary']}"),
            count=sig["count"],
            title=sig["title"][:100] if sig["title"] else sig["name"],
            summary=sig["summary"][:200] if sig["summary"] else f"{sig['name']} 情报信号 · {sig['platform_label']}",
        ))
        regions.add(sig["name"])
        platforms_set.add(platform)

    # 按信号数排序
    result_signals.sort(key=lambda s: s.count, reverse=True)

    return result_signals, len(result_signals), len(platforms_set), len(regions)


@router.get("/geo-signals", response_model=GeoSignalsResponse)
async def get_geo_signals(
    db: AsyncSession = Depends(get_db),
):
    """返回世界地图情报标注数据。免认证（只读仪表盘数据）。

    从近期监测结果 (最近 50 条) 和热门话题 (最近 30 条) 中
    提取地理位置关键词，按城市聚合为地图标注信号。
    """
    # ── Recent results (last 50) ──
    recent_query = (
        select(MonitorResult)
        .order_by(MonitorResult.created_at.desc())
        .limit(50)
    )
    recent_raw = (await db.execute(recent_query)).scalars().all()

    social_targets = (await db.execute(select(Target))).scalars().all()
    website_targets = (await db.execute(select(WebsiteTarget))).scalars().all()
    social_map = {t.id: (t.account_name, t.account_url, t.platform) for t in social_targets}
    website_map = {t.id: (t.name, t.url) for t in website_targets}

    recent_dicts = []
    for r in recent_raw:
        if r.target_type == "social_media":
            target_name, target_url, platform = social_map.get(
                r.target_id, (f"目标 #{r.target_id}", None, "unknown"))
        else:
            target_name, target_url = website_map.get(
                r.target_id, (f"网站 #{r.target_id}", None))
            platform = "website"
        recent_dicts.append({
            "target_name": target_name,
            "target_url": target_url,
            "platform": platform,
            "summary": r.summary,
            "raw_content": r.raw_content,
        })

    # ── Hot topics (last 30, distinct by platform+title) ──
    hot_topics_raw = []
    try:
        from models.hot_topic import HotTopic
        ht_query = (
            select(HotTopic)
            .order_by(HotTopic.fetched_at.desc().nullslast())
            .limit(30)
        )
        ht_raw = (await db.execute(ht_query)).scalars().all()
        hot_topics_raw = [
            {"title": t.title, "platform": t.platform, "hot_value": t.hot_value}
            for t in ht_raw
        ]
    except Exception:
        pass

    # ── Sentiment posts (last 200, scan title + content) ──
    sentiment_posts_raw = []
    try:
        from models.sentiment_post import SentimentPost
        sp_query = (
            select(SentimentPost.title, SentimentPost.content, SentimentPost.platform)
            .order_by(SentimentPost.fetched_at.desc().nullslast())
            .limit(200)
        )
        sp_rows = (await db.execute(sp_query)).all()
        sentiment_posts_raw = [
            {"title": row[0] or "", "content": row[1] or "", "platform": row[2] or ""}
            for row in sp_rows
        ]
    except Exception:
        pass

    # Extend hot_topics_raw with sentiment post titles for geo extraction
    for sp in sentiment_posts_raw:
        hot_topics_raw.append({
            "title": f"{sp['title']} {sp['content'][:200]}",
            "platform": sp['platform'],
            "hot_value": "",
        })

    signals, total, plat_count, region_count = _extract_geo_signals(
        recent_dicts, hot_topics_raw)

    return GeoSignalsResponse(
        signals=signals,
        total_signals=total,
        platforms_covered=plat_count,
        regions_covered=region_count,
    )
