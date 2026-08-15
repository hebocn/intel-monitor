# intel-monitor/backend/schemas/target.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TargetCreate(BaseModel):
    platform: str = Field(..., pattern="^(x|youtube|xiaohongshu|douyin|weibo|toutiao|108community)$")
    importance: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    account_name: str = Field(..., min_length=1, max_length=100)
    account_url: str = Field(..., max_length=500)
    avatar_url: Optional[str] = None
    monitor_interval_minutes: int = Field(default=1440, ge=60)
    monitor_hour: int = Field(default=9, ge=0, le=23)
    monitor_minute: int = Field(default=0, ge=0, le=59)
    cron_schedule: Optional[str] = Field(None, max_length=500)
    post_limit: int = Field(default=10, ge=1, le=100)
    post_time_range_days: int = Field(default=0, ge=0, le=365)
    is_active: bool = True


class TargetUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_url: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    monitor_interval_minutes: Optional[int] = Field(None, ge=60)
    monitor_hour: Optional[int] = Field(None, ge=0, le=23)
    monitor_minute: Optional[int] = Field(None, ge=0, le=59)
    cron_schedule: Optional[str] = Field(None, max_length=500)
    post_limit: Optional[int] = Field(None, ge=1, le=100)
    post_time_range_days: Optional[int] = Field(None, ge=0, le=365)
    importance: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    push_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class TargetResponse(BaseModel):
    id: int
    platform: str
    account_name: str
    account_url: str
    avatar_url: Optional[str]
    importance: Optional[str] = None
    monitor_interval_minutes: int
    monitor_hour: int
    monitor_minute: int
    cron_schedule: Optional[str]
    post_limit: int
    post_time_range_days: int
    opencli_ready: bool
    last_verify_status: str
    last_verify_method: Optional[str]
    push_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
