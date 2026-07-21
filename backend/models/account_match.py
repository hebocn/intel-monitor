# intel-monitor/backend/models/account_match.py
"""Account Match models — 账号比对模块"""
from datetime import datetime
from sqlalchemy import Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class AccountMatchTask(Base):
    __tablename__ = "account_match_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    target_name: Mapped[str] = mapped_column(String(100), nullable=False)
    platforms: Mapped[str] = mapped_column(String(200), nullable=False)  # JSON array
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_candidates: Mapped[int] = mapped_column(Integer, default=0)
    total_groups: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_mode: Mapped[str] = mapped_column(String(20), default="nickname")  # "profile" or "nickname"
    anchor_profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Scenario 1 anchor user's AI profile
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    candidates: Mapped[list["AccountMatchCandidate"]] = relationship(
        "AccountMatchCandidate", back_populates="task", cascade="all, delete-orphan",
        order_by="AccountMatchCandidate.match_score.desc()"
    )
    results: Mapped[list["AccountMatchResult"]] = relationship(
        "AccountMatchResult", back_populates="task", cascade="all, delete-orphan",
        order_by="AccountMatchResult.confidence_score.desc()"
    )


class AccountMatchCandidate(Base):
    __tablename__ = "account_match_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("account_match_tasks.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    platform_uid: Mapped[str] = mapped_column(String(200), nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    posts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    score_detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_with: Mapped[str | None] = mapped_column(String(200), nullable=True)

    task: Mapped["AccountMatchTask"] = relationship("AccountMatchTask", back_populates="candidates")


class AccountMatchResult(Base):
    __tablename__ = "account_match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("account_match_tasks.id"), nullable=False)
    group_label: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    account_ids_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of candidate IDs
    ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: per-dimension scores

    task: Mapped["AccountMatchTask"] = relationship("AccountMatchTask", back_populates="results")
