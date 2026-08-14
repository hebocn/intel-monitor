from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_targets: int
    active_targets: int
    total_websites: int
    today_results: int
    today_success: int
    today_failed: int

    # 新增：爬取方法分布
    crawl_method_opencli: int = 0
    crawl_method_cdp: int = 0
    crawl_method_playwright: int = 0
    crawl_method_scrapling: int = 0

    # 新增：平台覆盖数
    platforms_covered: int = 0


class TrendPoint(BaseModel):
    date: str
    total: int
    success: int
    failed: int


class PlatformStat(BaseModel):
    platform: str
    label: str
    count: int
    success: int
    failed: int
    success_rate: float


class RecentResultItem(BaseModel):
    id: int
    target_name: str
    target_url: str | None
    platform: str
    target_type: str
    status: str
    summary: str | None
    raw_content: str | None
    monitor_date: str
    created_at: str


class DashboardResponse(BaseModel):
    stats: DashboardStats
    recent_results: list[RecentResultItem]
    trend_data: list[TrendPoint] = []
    platform_stats: list[PlatformStat] = []


# ── Dashboard Overview (新端点) ──

class HotTopicPreview(BaseModel):
    title: str
    platform: str
    platform_label: str
    hot_value: str | None
    rank: int | None
    url: str | None


class SentimentSummary(BaseModel):
    total_tasks: int = 0
    total_posts: int = 0
    this_week_tasks: int = 0


class IntelligenceSummary(BaseModel):
    total_reports: int = 0
    in_progress: int = 0
    completed: int = 0


class SystemHealth(BaseModel):
    opencli_installed: bool = False
    opencli_running: bool = False
    cdp_connected: bool = False
    ai_provider: str = ""
    ai_model: str = ""


class DashboardOverviewResponse(BaseModel):
    hot_topics: list[HotTopicPreview] = []
    sentiment: SentimentSummary = SentimentSummary()
    intelligence: IntelligenceSummary = IntelligenceSummary()
    system_health: SystemHealth = SystemHealth()


# ── Geo Signals (世界地图情报标注) ──

class GeoSignal(BaseModel):
    name: str = ""
    lat: float
    lng: float
    platform: str
    platform_label: str
    color: str
    category: str
    count: int
    title: str
    summary: str


class GeoSignalsResponse(BaseModel):
    signals: list[GeoSignal]
    total_signals: int
    platforms_covered: int
    regions_covered: int
