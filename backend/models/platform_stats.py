# intel-monitor/backend/models/platform_stats.py
from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PlatformStats(Base):
    __tablename__ = "platform_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    metric: Mapped[str] = mapped_column(String(20), nullable=False)
    p50: Mapped[float] = mapped_column(Float, default=0.0)
    p75: Mapped[float] = mapped_column(Float, default=0.0)
    p90: Mapped[float] = mapped_column(Float, default=0.0)
    p95: Mapped[float] = mapped_column(Float, default=0.0)
    p99: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
