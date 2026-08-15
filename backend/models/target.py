# intel-monitor/backend/models/target.py
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # x/youtube/xiaohongshu/douyin/weibo
    importance: Mapped[str | None] = mapped_column(String(20), nullable=True)  # high/medium/low
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_url: Mapped[str] = mapped_column(String(500), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    monitor_hour: Mapped[int] = mapped_column(Integer, default=9)
    monitor_minute: Mapped[int] = mapped_column(Integer, default=0)
    cron_schedule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    post_limit: Mapped[int] = mapped_column(Integer, default=10)
    post_time_range_days: Mapped[int] = mapped_column(Integer, default=0)
    opencli_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verify_status: Mapped[str] = mapped_column(String(20), default="pending")
    last_verify_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
