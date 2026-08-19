# intel-monitor/backend/routers/account_prefs.py
from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.account_pref import AccountPref
from models.user import User
from schemas.account_pref import AccountPrefItem, AccountPrefResponse, AccountPrefSave

router = APIRouter(prefix="/api/account-prefs", tags=["account-prefs"])


@router.get("", response_model=list[AccountPrefResponse])
async def list_account_prefs(
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户已保存的平台分区内账号排序(按 sort_order 升序)。"""
    query = select(AccountPref).where(AccountPref.user_id == user.id)
    if platform:
        query = query.where(AccountPref.platform == platform)
    query = query.order_by(AccountPref.sort_order)
    result = await db.execute(query)
    return [
        AccountPrefResponse(target_id=p.target_id, platform=p.platform, sort_order=p.sort_order)
        for p in result.scalars().all()
    ]


@router.put("", response_model=list[AccountPrefResponse])
async def save_account_prefs(
    req: AccountPrefSave,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """全量保存某平台分区内的账号排序(先清该平台旧记录再写入)。"""
    await db.execute(
        delete(AccountPref).where(
            AccountPref.user_id == user.id, AccountPref.platform == req.platform
        )
    )
    for item in req.items:
        db.add(AccountPref(
            user_id=user.id, target_id=item.target_id, platform=req.platform, sort_order=item.sort_order,
        ))
    await db.commit()

    result = await db.execute(
        select(AccountPref)
        .where(AccountPref.user_id == user.id, AccountPref.platform == req.platform)
        .order_by(AccountPref.sort_order)
    )
    return [
        AccountPrefResponse(target_id=p.target_id, platform=p.platform, sort_order=p.sort_order)
        for p in result.scalars().all()
    ]


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def reset_account_prefs(
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """清空账号自定义排序(platform 为空时清全部,恢复 created_at 降序)。"""
    stmt = delete(AccountPref).where(AccountPref.user_id == user.id)
    if platform:
        stmt = stmt.where(AccountPref.platform == platform)
    await db.execute(stmt)
    await db.commit()