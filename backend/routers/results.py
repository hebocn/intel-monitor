# intel-monitor/backend/routers/results.py
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from auth import get_current_user
from models.user import User
from models.result import MonitorResult
from models.comment import HotComment
from schemas.result import ResultResponse, ResultDetailResponse, HotCommentResponse
from services.monitor import fetch_post_comments

router = APIRouter(prefix="/api/results", tags=["results"])


class FetchCommentsRequest(BaseModel):
    post_url: str


@router.get("", response_model=list[ResultResponse])
async def list_results(
    target_id: int | None = None,
    target_type: str | None = None,
    result_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(MonitorResult)
    if target_id:
        query = query.where(MonitorResult.target_id == target_id)
    if target_type:
        query = query.where(MonitorResult.target_type == target_type)
    if result_status:
        query = query.where(MonitorResult.status == result_status)
    query = query.order_by(MonitorResult.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{result_id}", response_model=ResultDetailResponse)
async def get_result_detail(
    result_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MonitorResult)
        .options(selectinload(MonitorResult.hot_comments))
        .where(MonitorResult.id == result_id)
    )
    monitor_result = result.scalar_one_or_none()
    if not monitor_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    return monitor_result


@router.post("/{result_id}/comments/fetch")
async def fetch_comments(
    result_id: int,
    body: FetchCommentsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按需抓取单帖热门评论并入库，随后后台异步 AI 精选全局 TOP10。"""
    return await fetch_post_comments(result_id, body.post_url)


@router.delete("/{result_id}")
async def delete_result(
    result_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MonitorResult).where(MonitorResult.id == result_id)
    )
    monitor_result = result.scalar_one_or_none()
    if not monitor_result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    await db.delete(monitor_result)
    await db.commit()
    return {"message": "删除成功"}
