# intel-monitor/backend/models/result.py
#
# Migration note (2026-04-30): Added `crawl_method` column.
# For existing SQLite databases, run manually:
#   ALTER TABLE monitor_results ADD COLUMN crawl_method VARCHAR(20);
#
from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MonitorResult(Base):
    __tablename__ = "monitor_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # social_media / website
    monitor_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # success/failed/pending
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawl_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # opencli/cdp/playwright
    comments_ai_status: Mapped[str] = mapped_column(String(20), default="idle")  # idle/selecting/done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    hot_comments = relationship("HotComment", backref="monitor_result", lazy="selectin")
