# intel-monitor/backend/schemas/result.py
from datetime import datetime, date, timedelta, timezone
from typing import Optional
from pydantic import BaseModel, field_serializer

BJT = timezone(timedelta(hours=8))


class HotCommentResponse(BaseModel):
    id: int
    post_url: str
    comment_text: str
    author: str
    likes_count: int
    reply_count: int = 0
    retweet_count: int = 0
    rank: int
    global_rank: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ResultResponse(BaseModel):
    id: int
    target_id: int
    target_type: str
    monitor_date: date
    summary: Optional[str]
    status: str
    error_message: Optional[str]
    crawl_method: Optional[str] = None
    comments_ai_status: str = "idle"
    created_at: datetime
    posts_count: Optional[int] = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime, _info):
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BJT).strftime("%Y-%m-%d %H:%M:%S")


class ResultDetailResponse(ResultResponse):
    raw_content: Optional[str]
    hot_comments: list[HotCommentResponse] = []
