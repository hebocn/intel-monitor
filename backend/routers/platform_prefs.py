# intel-monitor/backend/routers/platform_prefs.py
from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.platform_pref import PlatformPref
from models.user import User
from schemas.platform_pref import PlatformPrefItem, PlatformPrefSave

router = APIRouter(prefix="/api/platform-prefs", tags=["platform-prefs"])


@router.get("", response_model=list[PlatformPrefItem])
async def list_platform_prefs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户已保存的平台分区排序(按 sort_order 升序)。"""
    result = await db.execute(
        select(PlatformPref)
        .where(PlatformPref.user_id == user.id)
        .order_by(PlatformPref.sort_order)
    )
    return [PlatformPrefItem(platform=p.platform, sort_order=p.sort_order) for p in result.scalars().all()]


@router.put("", response_model=list[PlatformPrefItem])
async def save_platform_prefs(
    req: PlatformPrefSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全量保存当前用户的平台分区排序(先清空再写入)。"""
    await db.execute(delete(PlatformPref).where(PlatformPref.user_id == user.id))
    for item in req.items:
        db.add(PlatformPref(user_id=user.id, platform=item.platform, sort_order=item.sort_order))
    await db.commit()

    result = await db.execute(
        select(PlatformPref)
        .where(PlatformPref.user_id == user.id)
        .order_by(PlatformPref.sort_order)
    )
    return [PlatformPrefItem(platform=p.platform, sort_order=p.sort_order) for p in result.scalars().all()]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_platform_prefs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """清空自定义排序,恢复默认(账号数量降序)。"""
    await db.execute(delete(PlatformPref).where(PlatformPref.user_id == user.id))
    await db.commit()
