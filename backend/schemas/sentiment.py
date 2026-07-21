# intel-monitor/backend/schemas/sentiment.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SentimentSearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=200)
    platforms: list[str] = Field(..., min_length=1)
    post_limit: int = Field(default=20, ge=1, le=100)


class SentimentTaskResponse(BaseModel):
    id: int
    keyword: str
    platforms: str
    status: str
    total_posts: int
    error_log: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class SentimentTaskListResponse(BaseModel):
    tasks: list[SentimentTaskResponse]
    total: int
    page: int
    page_size: int


class SentimentPostResponse(BaseModel):
    id: int
    task_id: int
    platform: str
    post_id: str
    title: str
    content: str | None
    url: str
    author_name: str | None
    author_avatar: str | None
    author_followers: int
    published_at: datetime | None
    views: int
    likes: int
    comments: int
    shares: int
    bookmarks: int
    metrics_partial: bool
    engagement_score: float
    platform_weight: float
    time_decay: float
    impact_score: float
    images_json: str | None
    videos_json: str | None
    comments_json: str | None
    quoted_tweet_json: str | None = None
    card_json: str | None = None
    score_detail: str | None
    fetched_at: datetime
    deep_analysis_status: str | None = None

    model_config = {"from_attributes": True}


class SentimentTaskDetailResponse(SentimentTaskResponse):
    posts: list[SentimentPostResponse]


class SentimentPlatformInfo(BaseModel):
    platform: str
    label: str
    supported_metrics: list[str]
