# intel-monitor/backend/models/sentiment_task.py
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SentimentTask(Base):
    __tablename__ = "sentiment_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    platforms: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    posts: Mapped[list["SentimentPost"]] = relationship(
        "SentimentPost", back_populates="task", cascade="all, delete-orphan",
        order_by="SentimentPost.sort_order.asc()"
    )
