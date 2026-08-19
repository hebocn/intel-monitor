# intel-monitor/backend/models/tag.py
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Table, Column, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base

# 账号-标签 多对多关联
target_tags = Table(
    "target_tags",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("target_id", Integer, ForeignKey("targets.id"), nullable=False),
    Column("tag_id", Integer, ForeignKey("tags.id"), nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    UniqueConstraint("target_id", "tag_id", name="uq_target_tag"),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#94A3B8")
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_tag_name"),)
