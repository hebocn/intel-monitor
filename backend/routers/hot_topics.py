import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from auth import get_current_user
from models.user import User
from models.hot_topic_source import HotTopicSource
from models.hot_topic import HotTopic
from schemas.hot_topic import (
    HotTopicSourceCreate, HotTopicSourceUpdate, HotTopicSourceResponse,
    HotTopicResponse, FetchRequest,
)
from services.autocli_service import (
    PLATFORM_CMD, PLATFORM_LABELS, PLATFORM_MODES,
    fetch_hot_topics, fetch_multiple,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["hot-topics"])


# ─── Platforms ────────────────────────────────────────────────────

@router.get("/api/hot-topic-sources/platforms")
async def list_platforms():
    """Return supported platforms with labels and modes."""
    return [
        {"key": k, "label": PLATFORM_LABELS.get(k, k), "mode": PLATFORM_MODES.get(k, "public")}
        for k in PLATFORM_CMD
    ]


# ─── HotTopicSource CRUD ─────────────────────────────────────────

@router.get("/api/hot-topic-sources", response_model=list[HotTopicSourceResponse])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HotTopicSource)
        .where(HotTopicSource.user_id == user.id)
        .order_by(HotTopicSource.created_at.desc())
    )
    return result.scalars().all()


@router.post("/api/hot-topic-sources", response_model=HotTopicSourceResponse, status_code=201)
async def create_source(
    req: HotTopicSourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if req.platform not in PLATFORM_CMD:
        raise HTTPException(400, f"不支持的平台: {req.platform}")

    # Check duplicate
    existing = await db.execute(
        select(HotTopicSource).where(
            HotTopicSource.user_id == user.id,
            HotTopicSource.platform == req.platform,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"平台「{PLATFORM_LABELS.get(req.platform, req.platform)}」已添加")

    source = HotTopicSource(user_id=user.id, **req.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.put("/api/hot-topic-sources/{source_id}", response_model=HotTopicSourceResponse)
async def update_source(
    source_id: int,
    req: HotTopicSourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HotTopicSource).where(
            HotTopicSource.id == source_id,
            HotTopicSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "平台配置不存在")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/api/hot-topic-sources/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(HotTopicSource).where(
            HotTopicSource.id == source_id,
            HotTopicSource.user_id == user.id,
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(404, "平台配置不存在")

    # Delete associated topics
    await db.execute(delete(HotTopic).where(HotTopic.source_id == source_id))
    await db.delete(source)
    await db.commit()


# ─── HotTopic queries ────────────────────────────────────────────

@router.get("/api/hot-topics", response_model=list[HotTopicResponse])
async def list_topics(
    platform: str | None = None,
    source_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(HotTopic)

    # Filter by user's sources
    user_sources = await db.execute(
        select(HotTopicSource.id).where(HotTopicSource.user_id == user.id)
    )
    source_ids = [row[0] for row in user_sources.all()]
    if not source_ids:
        return []

    query = query.where(HotTopic.source_id.in_(source_ids))

    if platform:
        query = query.where(HotTopic.platform == platform)
    if source_id:
        query = query.where(HotTopic.source_id == source_id)

    query = query.order_by(HotTopic.platform, HotTopic.rank)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/api/hot-topics/fetch")
async def trigger_fetch(
    req: FetchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Launch hot topics fetch in background. Returns immediately."""
    if req.source_id:
        result = await db.execute(
            select(HotTopicSource).where(
                HotTopicSource.id == req.source_id,
                HotTopicSource.user_id == user.id,
            )
        )
        source = result.scalar_one_or_none()
        if not source:
            raise HTTPException(404, "平台配置不存在")
        sources = [source]
    else:
        result = await db.execute(
            select(HotTopicSource).where(
                HotTopicSource.user_id == user.id,
                HotTopicSource.is_active == True,
            )
        )
        sources = result.scalars().all()
        if req.platforms:
            sources = [s for s in sources if s.platform in req.platforms]
        if not sources:
            raise HTTPException(400, "没有已启用的平台，请先添加并启用平台")

    platforms = [s.platform for s in sources]
    source_map = {s.platform: s for s in sources}

    import asyncio
    asyncio.create_task(_fetch_and_store(platforms, source_map))

    labels = ', '.join(PLATFORM_LABELS.get(p, p) for p in platforms)
    return {
        "message": f"抓取已启动，后台获取 {len(platforms)} 个平台：{labels}",
        "success": 0, "errors": 0, "total": 0,
        "pending": True,
    }


async def _fetch_and_store(platforms: list[str], source_map: dict):
    """Background task: fetch topics and store to DB."""
    results = await fetch_multiple(platforms)

    async with async_session() as db:
        for platform, topics_or_error in results.items():
            source = source_map.get(platform)
            if not source:
                continue

            if isinstance(topics_or_error, str):
                logger.error(f"[HotTopics] {platform} fetch failed: {topics_or_error}")
                continue

            topics = topics_or_error

            # Delete old topics for this source
            await db.execute(delete(HotTopic).where(HotTopic.source_id == source.id))

            # Insert new topics
            now = datetime.now(timezone.utc)
            for t in topics:
                db.add(HotTopic(
                    source_id=source.id,
                    platform=platform,
                    title=t.title,
                    url=t.url,
                    rank=t.rank,
                    hot_value=t.hot_value,
                    extra=str(t.extra) if t.extra else None,
                    fetched_at=now,
                ))

            logger.info(f"[HotTopics] Stored {len(topics)} topics for {platform}")

        await db.commit()


@router.delete("/api/hot-topics/{topic_id}", status_code=204)
async def delete_topic(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify ownership via source
    result = await db.execute(select(HotTopic).where(HotTopic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(404, "话题不存在")

    source_result = await db.execute(
        select(HotTopicSource).where(
            HotTopicSource.id == topic.source_id,
            HotTopicSource.user_id == user.id,
        )
    )
    if not source_result.scalar_one_or_none():
        raise HTTPException(404, "话题不存在")

    await db.delete(topic)
    await db.commit()


@router.delete("/api/hot-topics/clear")
async def clear_topics(
    platform: str | None = None,
    source_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Clear topics by platform or source_id."""
    user_sources = await db.execute(
        select(HotTopicSource.id).where(HotTopicSource.user_id == user.id)
    )
    source_ids = [row[0] for row in user_sources.all()]
    if not source_ids:
        return {"deleted": 0}

    query = delete(HotTopic).where(HotTopic.source_id.in_(source_ids))
    if platform:
        query = query.where(HotTopic.platform == platform)
    if source_id:
        query = query.where(HotTopic.source_id == source_id)

    result = await db.execute(query)
    await db.commit()
    return {"deleted": result.rowcount}


# ─── Execute fetch (called by scheduler) ─────────────────────────

async def execute_hot_topic_fetch(source_id: int):
    """Fetch and store hot topics for a single source (called by scheduler)."""
    async with async_session() as db:
        result = await db.execute(
            select(HotTopicSource).where(HotTopicSource.id == source_id)
        )
        source = result.scalar_one_or_none()
        if not source or not source.is_active:
            return

        source_map = {source.platform: source}
        await _fetch_and_store([source.platform], source_map)
