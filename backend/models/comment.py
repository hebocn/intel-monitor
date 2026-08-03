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
    reply_count: Mapped[int] = mapped_column(Integer, default=0)  # 评论底下的回复数（微博 hotflow）
    retweet_count: Mapped[int] = mapped_column(Integer, default=0)  # 评论被转发数（X thread）
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 帖内排名 1-10
    global_rank: Mapped[int] = mapped_column(Integer, default=0)  # 全局 TOP10 排名，0=未入选
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
