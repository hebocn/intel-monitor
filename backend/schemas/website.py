# intel-monitor/backend/schemas/website.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class WebsiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., max_length=500)
    css_selector: Optional[str] = Field(None, max_length=200)
    monitor_interval_minutes: int = Field(default=1440, ge=60)
    monitor_hour: int = Field(default=9, ge=0, le=23)
    monitor_minute: int = Field(default=0, ge=0, le=59)
    is_active: bool = True


class WebsiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, max_length=500)
    css_selector: Optional[str] = Field(None, max_length=200)
    monitor_interval_minutes: Optional[int] = Field(None, ge=60)
    monitor_hour: Optional[int] = Field(None, ge=0, le=23)
    monitor_minute: Optional[int] = Field(None, ge=0, le=59)
    push_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class WebsiteResponse(BaseModel):
    id: int
    name: str
    url: str
    css_selector: Optional[str]
    monitor_interval_minutes: int
    monitor_hour: int
    monitor_minute: int
    push_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
