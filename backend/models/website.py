# intel-monitor/backend/models/website.py
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class WebsiteTarget(Base):
    __tablename__ = "website_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    css_selector: Mapped[str | None] = mapped_column(String(200), nullable=True)
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    monitor_hour: Mapped[int] = mapped_column(Integer, default=9)
    monitor_minute: Mapped[int] = mapped_column(Integer, default=0)
    cron_schedule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
