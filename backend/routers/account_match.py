# intel-monitor/backend/routers/account_match.py
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db, async_session
from models.user import User
from models.account_match import AccountMatchTask, AccountMatchCandidate, AccountMatchResult
from schemas.account_match import (
    AccountMatchSearchRequest,
    AccountMatchTaskResponse,
    AccountMatchTaskListResponse,
    AccountMatchTaskDetailResponse,
    AccountMatchCandidateResponse,
    AccountMatchResultResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account-match", tags=["account-match"])

SUPPORTED_PLATFORMS = {"weibo", "x"}


@router.post("/search")
async def create_account_match(
    req: AccountMatchSearchRequest,
    user: User = Depends(get_current_user),
):
    invalid = [p for p in req.platforms if p not in SUPPORTED_PLATFORMS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {invalid}")

    async with async_session() as db:
        task = AccountMatchTask(
            user_id=user.id,
            target_name=req.target_name,
            platforms=json.dumps(req.platforms, ensure_ascii=False),
            status="pending",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        from services.account_matcher import run_account_match
        asyncio.create_task(
            run_account_match(task.id, req.target_name, req.platforms, req.match_mode, req.anchor_platform)
        )

        return {
            "task_id": task.id,
            "status": "pending",
            "message": f"账号比对已启动：{req.target_name}，平台：{', '.join(req.platforms)}",
        }


@router.get("/tasks", response_model=AccountMatchTaskListResponse)
async def list_tasks(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = (
        select(AccountMatchTask)
        .where(AccountMatchTask.user_id == user.id)
        .order_by(AccountMatchTask.created_at.desc())
        .limit(50)
    )
    tasks = (await db.execute(stmt)).scalars().all()

    return AccountMatchTaskListResponse(
        tasks=[AccountMatchTaskResponse.model_validate(t) for t in tasks],
        total=len(tasks),
    )


@router.get("/tasks/{task_id}", response_model=AccountMatchTaskDetailResponse)
async def get_task_detail(
    task_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = (
        select(AccountMatchTask)
        .where(AccountMatchTask.id == task_id, AccountMatchTask.user_id == user.id)
        .options(
            selectinload(AccountMatchTask.candidates),
            selectinload(AccountMatchTask.results),
        )
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return AccountMatchTaskDetailResponse(
        id=task.id,
        target_name=task.target_name,
        platforms=task.platforms,
        status=task.status,
        match_mode=task.match_mode or "nickname",
        total_candidates=task.total_candidates,
        total_groups=task.total_groups,
        error_log=task.error_log,
        anchor_profile_json=task.anchor_profile_json,
        created_at=task.created_at,
        completed_at=task.completed_at,
        candidates=[AccountMatchCandidateResponse.model_validate(c) for c in task.candidates],
        results=[AccountMatchResultResponse.model_validate(r) for r in task.results],
    )


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(AccountMatchTask).where(
        AccountMatchTask.id == task_id,
        AccountMatchTask.user_id == user.id,
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    await db.execute(delete(AccountMatchResult).where(AccountMatchResult.task_id == task_id))
    await db.execute(delete(AccountMatchCandidate).where(AccountMatchCandidate.task_id == task_id))
    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除"}
