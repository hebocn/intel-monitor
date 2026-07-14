from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_targets: int
    active_targets: int
    total_websites: int
    today_results: int
    today_success: int
    today_failed: int


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
