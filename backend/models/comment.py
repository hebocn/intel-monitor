# intel-monitor/backend/models/comment.py
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class HotComment(Base):
    __tablename__ = "hot_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_result_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_results.id"), nullable=False)
    post_url: Mapped[str] = mapped_column(String(500), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
