# intel-monitor/backend/routers/targets.py
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from auth import get_current_user
from models.user import User
from models.target import Target
from models.tag import Tag, target_tags
from schemas.target import TargetCreate, TargetUpdate, TargetResponse
from schemas.tag import TagBrief, TargetTagSetRequest, TargetTagBatchRequest
from services.importer import make_target_template, import_targets

router = APIRouter(prefix="/api/targets", tags=["targets"])

logger = logging.getLogger(__name__)


async def _warm_and_verify(target_id: int):
    """Pre-warm OpenCLI session and verify the target with a test crawl."""
    from services.monitor import crawl_with_fallback
    from crawlers.opencli_crawler import _check_opencli, crawl_with_opencli, _extract_username, PLATFORM_CMD

    async with async_session() as db:
        result = await db.execute(select(Target).where(Target.id == target_id))
        target = result.scalar_one_or_none()
        if not target:
            return

        # Step 1: OpenCLI pre-warm
        opencli_ready = False
        if target.platform in PLATFORM_CMD and _check_opencli():
            try:
                username = _extract_username(target.platform, target.account_url, target.account_name)
                await crawl_with_opencli(target.platform, target.account_name, target.account_url, limit=3)
                opencli_ready = True
            except Exception as e:
                logger.warning(f"OpenCLI pre-warm failed for target {target_id}: {e}")

        target.opencli_ready = opencli_ready

        # Step 2: Verify with fallback crawl
        try:
            crawl_result, method, error_log = await crawl_with_fallback(
                platform=target.platform,
                account_name=target.account_name,
                account_url=target.account_url,
                post_limit=3,
            )

            if crawl_result and crawl_result.success:
                target.last_verify_status = "success"
                target.last_verify_method = method
            else:
                target.last_verify_status = "failed"
                target.last_verify_method = method
        except Exception as e:
            target.last_verify_status = "failed"
            logger.warning(f"Verification failed for target {target_id}: {e}")

        await db.commit()


async def _attach_tags(db: AsyncSession, targets: list[Target]) -> None:
    """批量查询账号-标签关联并挂到 ORM 对象上（供 TargetResponse 序列化）。"""
    if not targets:
        return
    rows = await db.execute(
        select(target_tags.c.target_id, Tag)
        .join(Tag, Tag.id == target_tags.c.tag_id)
        .where(target_tags.c.target_id.in_([t.id for t in targets]))
        .order_by(Tag.created_at.asc(), Tag.id.asc())
    )
    by_target: dict[int, list[TagBrief]] = {}
    for target_id, tag in rows.all():
        by_target.setdefault(target_id, []).append(TagBrief.model_validate(tag))
    for t in targets:
        setattr(t, "tags", by_target.get(t.id, []))


@router.get("", response_model=list[TargetResponse])
async def list_targets(
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Target).where(Target.user_id == user.id)
    if platform:
        query = query.where(Target.platform == platform)
    query = query.order_by(Target.created_at.desc())
    result = await db.execute(query)
    targets = result.scalars().all()
    await _attach_tags(db, list(targets))
    return targets


@router.post("", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
async def create_target(
    req: TargetCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = Target(user_id=user.id, **req.model_dump())
    db.add(target)
    await db.commit()
    await db.refresh(target)
    setattr(target, "tags", [])

    # Trigger async pre-warm and verification
    background_tasks.add_task(_warm_and_verify, target.id)

    return target


class TargetBatchUpdateRequest(BaseModel):
    """批量修改：target_ids 必填；is_active / push_enabled 未提供则保持不变。"""
    target_ids: list[int] = Field(..., min_length=1)
    is_active: bool | None = None
    push_enabled: bool | None = None


@router.post("/batch-update")
async def batch_update_targets(
    req: TargetBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量更新监测（is_active）与飞书推送（push_enabled）开关。"""
    updates = {}
    if req.is_active is not None:
        updates["is_active"] = req.is_active
    if req.push_enabled is not None:
        updates["push_enabled"] = req.push_enabled
    if not updates:
        raise HTTPException(status_code=400, detail="至少需要提供 is_active 或 push_enabled")

    result = await db.execute(
        select(Target).where(
            Target.id.in_(req.target_ids),
            Target.user_id == user.id,
        )
    )
    targets = result.scalars().all()
    if not targets:
        raise HTTPException(status_code=404, detail="未找到匹配的社交账号目标")
    for t in targets:
        for k, v in updates.items():
            setattr(t, k, v)
    await db.commit()
    return {"updated": len(targets), "fields": list(updates.keys())}


@router.put("/{target_id}", response_model=TargetResponse)
async def update_target(
    target_id: int,
    req: TargetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    await db.commit()
    await db.refresh(target)
    await _attach_tags(db, [target])
    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    await db.execute(delete(target_tags).where(target_tags.c.target_id == target_id))
    await db.delete(target)
    await db.commit()


# ── 账号打标签 ─────────────────────────────────────────────

async def _validate_owned_tags(db: AsyncSession, user_id: int, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    result = await db.execute(
        select(Tag).where(Tag.user_id == user_id, Tag.id.in_(tag_ids))
    )
    tags = result.scalars().all()
    if len(tags) != len(set(tag_ids)):
        raise HTTPException(status_code=400, detail="存在无效或不属于当前用户的标签")
    return tags


@router.put("/{target_id}/tags", response_model=TargetResponse)
async def set_target_tags(
    target_id: int,
    req: TargetTagSetRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """整体替换单个账号的标签集合。"""
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    await _validate_owned_tags(db, user.id, req.tag_ids)
    await db.execute(delete(target_tags).where(target_tags.c.target_id == target_id))
    for tag_id in dict.fromkeys(req.tag_ids):  # 去重保序
        await db.execute(target_tags.insert().values(target_id=target_id, tag_id=tag_id))
    await db.commit()
    await db.refresh(target)
    await _attach_tags(db, [target])
    return target


@router.post("/batch-tags")
async def batch_set_target_tags(
    req: TargetTagBatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量为多个账号添加/移除标签。"""
    if not req.add_tag_ids and not req.remove_tag_ids:
        raise HTTPException(status_code=400, detail="请至少选择要添加或移除的标签")

    result = await db.execute(
        select(Target).where(Target.id.in_(req.target_ids), Target.user_id == user.id)
    )
    targets = result.scalars().all()
    if not targets:
        raise HTTPException(status_code=404, detail="未找到匹配的社交账号目标")
    target_ids = [t.id for t in targets]

    await _validate_owned_tags(db, user.id, req.add_tag_ids + req.remove_tag_ids)
    if req.remove_tag_ids:
        await db.execute(
            delete(target_tags).where(
                target_tags.c.target_id.in_(target_ids),
                target_tags.c.tag_id.in_(req.remove_tag_ids),
            )
        )
    if req.add_tag_ids:
        existing = await db.execute(
            select(target_tags.c.target_id, target_tags.c.tag_id).where(
                target_tags.c.target_id.in_(target_ids),
                target_tags.c.tag_id.in_(req.add_tag_ids),
            )
        )
        existing_pairs = set(existing.all())
        for tid in target_ids:
            for tag_id in dict.fromkeys(req.add_tag_ids):
                if (tid, tag_id) not in existing_pairs:
                    await db.execute(target_tags.insert().values(target_id=tid, tag_id=tag_id))
    await db.commit()
    return {"updated": len(target_ids)}


# ── 批量导入 ─────────────────────────────────────────────

@router.get("/import/template")
async def download_target_template(user: User = Depends(get_current_user)):
    """下载社交账号批量导入模板（xlsx，列名固定：平台 / 账号名称 / 账号URL）。"""
    content = make_target_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="target_import_template.xlsx"'},
    )


@router.post("/import")
async def import_targets_batch(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量导入社交账号（xlsx/xls/csv）。列名必须为：平台 / 账号名称 / 账号URL。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        existing = (await db.execute(
            select(Target.account_url).where(Target.user_id == user.id)
        )).scalars().all()
        existing_urls = {u.lower().rstrip("/") for u in existing if u}

        result, items = import_targets(file.filename or "upload.xlsx", data, existing_urls)
        for item in items:
            db.add(Target(user_id=user.id, **item))
        await db.commit()

        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("[import] 社交账号批量导入失败")
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")
