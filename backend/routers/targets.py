# intel-monitor/backend/routers/targets.py
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from auth import get_current_user
from models.user import User
from models.target import Target
from schemas.target import TargetCreate, TargetUpdate, TargetResponse
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
    return result.scalars().all()


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

    # Trigger async pre-warm and verification
    background_tasks.add_task(_warm_and_verify, target.id)

    return target


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
    await db.delete(target)
    await db.commit()


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
