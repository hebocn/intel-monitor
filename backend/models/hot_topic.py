from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from database import Base


class HotTopic(Base):
    __tablename__ = "hot_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("hot_topic_sources.id"), nullable=False)
    platform = Column(String, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=True)
    rank = Column(Integer, nullable=True)
    hot_value = Column(String, nullable=True)
    extra = Column(Text, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now())
