# intel-monitor/backend/models/sentiment_post.py
from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SentimentPost(Base):
    __tablename__ = "sentiment_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("sentiment_tasks.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    post_id: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    author_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    author_avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author_followers: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    bookmarks: Mapped[int] = mapped_column(Integer, default=0)
    metrics_partial: Mapped[bool] = mapped_column(Boolean, default=False)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    platform_weight: Mapped[float] = mapped_column(Float, default=0.0)
    time_decay: Mapped[float] = mapped_column(Float, default=0.0)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    images_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    videos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deep_analysis_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)

    task: Mapped["SentimentTask"] = relationship("SentimentTask", back_populates="posts")
