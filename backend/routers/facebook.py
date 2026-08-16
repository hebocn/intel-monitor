# intel-monitor/backend/routers/facebook.py
"""Facebook 辅助接口 — 添加监测目标时按昵称反查候选主页。"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import get_current_user
from models.user import User
from crawlers.base import _run_crawler_in_thread

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/facebook", tags=["facebook"])


class FacebookAccountSearchRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=100, description="昵称关键词")
    limit: int = Field(8, ge=1, le=20)


@router.post("/search")
async def search_facebook_accounts(
    req: FacebookAccountSearchRequest,
    user: User = Depends(get_current_user),
):
    """按昵称用 Google CSE 反查 facebook.com 主页候选列表。

    返回候选列表供用户在添加监测目标时点选,自动填充 account_name + account_url。
    """
    from crawlers.facebook_crawler import search_facebook_accounts

    candidates = await _run_crawler_in_thread(
        search_facebook_accounts(req.nickname, req.limit)
    )
    return {"candidates": candidates}
