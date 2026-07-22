# intel-monitor/backend/routers/sentiment.py
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db, async_session
from models.user import User
from models.sentiment_task import SentimentTask
from models.sentiment_post import SentimentPost
from schemas.sentiment import (
    SentimentSearchRequest,
    SentimentTaskResponse,
    SentimentTaskListResponse,
    SentimentTaskDetailResponse,
    SentimentPostResponse,
    SentimentPlatformInfo,
)
from services.scoring import PLATFORM_MAU_DEFAULTS, DEFAULT_HALF_LIFE_DAYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])

PLATFORM_INFO = {
    "weibo": {"label": "微博", "metrics": ["likes", "comments", "shares"]},
    "douyin": {"label": "抖音", "metrics": ["likes", "comments", "shares"]},
    "xiaohongshu": {"label": "小红书", "metrics": ["likes", "comments", "bookmarks"]},
    "toutiao": {"label": "今日头条", "metrics": ["comments"]},
    "108community": {"label": "108天台社区", "metrics": ["comments"]},
    "youtube": {"label": "YouTube", "metrics": ["views", "likes", "comments"]},
    "x": {"label": "X (Twitter)", "metrics": ["views", "likes", "comments", "shares", "bookmarks"]},
    "facebook": {"label": "Facebook", "metrics": ["likes", "comments", "shares"]},
}


@router.get("/platforms")
async def list_platforms(user: User = Depends(get_current_user)):
    return [
        SentimentPlatformInfo(
            platform=k,
            label=v["label"],
            supported_metrics=v["metrics"],
        )
        for k, v in PLATFORM_INFO.items()
    ]


@router.post("/search")
async def create_sentiment_search(
    req: SentimentSearchRequest,
    user: User = Depends(get_current_user),
):
    invalid = [p for p in req.platforms if p not in PLATFORM_INFO]
    if invalid:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {invalid}")

    async with async_session() as db:
        task = SentimentTask(
            user_id=user.id,
            keyword=req.keyword,
            platforms=json.dumps(req.platforms, ensure_ascii=False),
            status="pending",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        from services.sentiment import run_sentiment_search
        asyncio.create_task(
            run_sentiment_search(task.id, req.keyword, req.platforms, req.post_limit)
        )

        labels = [PLATFORM_INFO[p]["label"] for p in req.platforms if p in PLATFORM_INFO]
        return {
            "task_id": task.id,
            "status": "pending",
            "message": f"搜索已启动：{req.keyword}，平台：{', '.join(labels)}",
        }


@router.get("/tasks", response_model=SentimentTaskListResponse)
async def list_tasks(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(SentimentTask).where(SentimentTask.user_id == user.id)
    if status:
        stmt = stmt.where(SentimentTask.status == status)
    stmt = stmt.order_by(SentimentTask.created_at.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    tasks = (await db.execute(stmt)).scalars().all()

    return SentimentTaskListResponse(
        tasks=[SentimentTaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/tasks/{task_id}", response_model=SentimentTaskDetailResponse)
async def get_task_detail(
    task_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = (
        select(SentimentTask)
        .where(SentimentTask.id == task_id, SentimentTask.user_id == user.id)
        .options(selectinload(SentimentTask.posts))
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return SentimentTaskDetailResponse(
        id=task.id,
        keyword=task.keyword,
        platforms=task.platforms,
        status=task.status,
        total_posts=task.total_posts,
        error_log=task.error_log,
        created_at=task.created_at,
        completed_at=task.completed_at,
        posts=[SentimentPostResponse.model_validate(p) for p in task.posts],
    )


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(SentimentTask).where(
        SentimentTask.id == task_id, SentimentTask.user_id == user.id
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    await db.execute(
        delete(SentimentPost).where(SentimentPost.task_id == task_id)
    )
    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除"}


# ── Deep Analysis (YouTube) ─────────────────────────────────────────


@router.post("/posts/{post_id}/deep-analyze")
async def trigger_deep_analysis(
    post_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Trigger deep analysis for a YouTube video (audio download → Whisper → LLM summary).

    Sets deep_analysis_status to 'processing' and spawns a background task.
    Returns immediately with the current status.
    """
    stmt = select(SentimentPost).where(SentimentPost.id == post_id)
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    if post.platform != "youtube":
        raise HTTPException(status_code=400, detail="仅 YouTube 视频支持深度分析")
    if post.deep_analysis_status == "processing":
        return {"status": "processing", "message": "深度分析正在执行中"}

    # Mark processing
    post.deep_analysis_status = "processing"
    await db.commit()

    # Spawn background task
    from services.youtube_deep import run_deep_analysis
    asyncio.create_task(run_deep_analysis(post.id, post.url))

    return {"status": "processing", "message": "深度分析已启动"}


@router.get("/posts/{post_id}/deep-analyze")
async def get_deep_analysis_status(
    post_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Get deep analysis status for a post."""
    stmt = select(SentimentPost).where(SentimentPost.id == post_id)
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="帖子不存在")
    return {"status": post.deep_analysis_status or "idle"}
