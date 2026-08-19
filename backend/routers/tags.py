# intel-monitor/backend/routers/tags.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.tag import Tag, target_tags
from schemas.tag import TagCreate, TagUpdate, TagResponse

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Tag).where(Tag.user_id == user.id).order_by(Tag.created_at.asc(), Tag.id.asc())
    )
    tags = result.scalars().all()
    counts: dict[int, int] = {}
    if tags:
        rows = await db.execute(
            select(target_tags.c.tag_id, func.count())
            .where(target_tags.c.tag_id.in_([t.id for t in tags]))
            .group_by(target_tags.c.tag_id)
        )
        counts = dict(rows.all())
    out = []
    for t in tags:
        resp = TagResponse.model_validate(t)
        resp.target_count = counts.get(t.id, 0)
        out.append(resp)
    return out


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    req: TagCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dup = await db.execute(
        select(Tag).where(Tag.user_id == user.id, Tag.name == req.name.strip())
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"标签「{req.name}」已存在")
    tag = Tag(user_id=user.id, name=req.name.strip(), color=req.color, is_preset=False)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagResponse.model_validate(tag)


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: int,
    req: TagUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    data = req.model_dump(exclude_unset=True)
    if "name" in data:
        name = data["name"].strip()
        if name != tag.name:
            dup = await db.execute(
                select(Tag).where(Tag.user_id == user.id, Tag.name == name, Tag.id != tag.id)
            )
            if dup.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"标签「{name}」已存在")
        tag.name = name
    if "color" in data and data["color"]:
        tag.color = data["color"]
    await db.commit()
    await db.refresh(tag)

    count = await db.execute(
        select(func.count()).select_from(target_tags).where(target_tags.c.tag_id == tag.id)
    )
    resp = TagResponse.model_validate(tag)
    resp.target_count = count.scalar() or 0
    return resp


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除标签，并连带解除所有账号上的该标签。"""
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    removed = await db.execute(
        delete(target_tags).where(target_tags.c.tag_id == tag.id)
    )
    await db.delete(tag)
    await db.commit()
    return {"removed_links": removed.rowcount or 0}
