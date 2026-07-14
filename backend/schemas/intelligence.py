# intel-monitor/backend/schemas/intelligence.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Category ────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    level: int = Field(..., ge=1, le=3)
    parent_id: Optional[int] = None
    sort_order: int = 0

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class CategoryTree(BaseModel):
    id: int
    name: str
    level: int
    sort_order: int
    children: list["CategoryTree"] = []

    model_config = {"from_attributes": True}


# ── Report ──────────────────────────────────────────────────────────────────

class ReportGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=10, max_length=3000)
    category_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=200)
    # 搜索引擎 + web 搜索覆盖
    search_engines: list[str] = Field(
        default=["firecrawl"],
        description="Search engines: firecrawl (=Google/Bing via Firecrawl)"
    )
    # 平台爬虫覆盖
    crawl_platforms: list[str] = Field(
        default=[],
        description="Internal platform crawlers: weibo/douyin/xiaohongshu/toutiao/108community"
    )
    max_search_results: int = Field(default=10, ge=1, le=100)
    max_sources: int = Field(default=30, ge=5, le=200)
    half_life_days: float = Field(default=30.0, ge=1.0, le=365.0)  # 情报报告时间窗口更宽

class ReportProgressResponse(BaseModel):
    id: int  # maps to model.id
    status: str
    title: str
    topic: str
    category_id: Optional[int]
    progress_detail: Optional[str] = None
    error_log: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ReportDetailResponse(ReportProgressResponse):
    search_queries: Optional[str] = None
    search_platforms: Optional[str] = None
    report_markdown: Optional[str] = None
    sources_json: Optional[str] = None

    model_config = {"from_attributes": True}

class ReportListItem(BaseModel):
    id: int
    title: str
    status: str
    category_id: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ReportListResponse(BaseModel):
    reports: list[ReportListItem]
    total: int
    page: int
    page_size: int

class GenerateResponse(BaseModel):
    report_id: int
    status: str
    message: str

class ExportRequest(BaseModel):
    format: str = Field(default="docx", pattern="^(docx|pdf)$")
