from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from database import Base


class HotTopicSource(Base):
    __tablename__ = "hot_topic_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    cron_schedule = Column(String, nullable=True)
    item_limit = Column(Integer, default=30)
    created_at = Column(DateTime, server_default=func.now())
