# intel-monitor/backend/models/intelligence_report.py
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class IntelligenceReport(Base):
    __tablename__ = "intelligence_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("intelligence_categories.id"), nullable=True
    )
    search_queries: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    search_platforms: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress_detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    category: Mapped["IntelligenceCategory | None"] = relationship("IntelligenceCategory")
