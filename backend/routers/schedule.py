from datetime import date

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from services.scheduler import refresh_jobs, get_job_status
from services.monitor import execute_monitor
from crawlers.opencli_crawler import crawl_with_opencli, _check_opencli

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/status")
async def schedule_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Fetch target names for enrichment
    targets = (await db.execute(select(Target))).scalars().all()
    websites = (await db.execute(select(WebsiteTarget))).scalars().all()
    name_map: dict[str, str] = {}
    for t in targets:
        name_map[f"target_{t.id}"] = t.account_name
    for w in websites:
        name_map[f"website_{w.id}"] = w.name

    jobs = get_job_status()
    for job in jobs:
        # Parse job id like "target_1", "target_1_0", "website_2", "website_2_0"
        job_id = job["id"]
        # Try base key first, then parent key
        if job_id in name_map:
            job["target_name"] = name_map[job_id]
        else:
            # e.g. "target_1_0" → look for "target_1"
            parts = job_id.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_key = parts[0]
                job["target_name"] = name_map.get(base_key, base_key)
            else:
                job["target_name"] = job_id

    return {"jobs": jobs}


@router.post("/refresh")
async def refresh_schedule(user: User = Depends(get_current_user)):
    await refresh_jobs()
    return {"message": "Schedule refreshed"}


@router.post("/run/{target_id}")
async def run_now(
    target_id: int,
    target_type: str = "social_media",
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate target exists
    if target_type == "social_media":
        target_check = await db.execute(select(Target).where(Target.id == target_id))
    else:
        target_check = await db.execute(select(WebsiteTarget).where(WebsiteTarget.id == target_id))
    if not target_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Target not found")

    # Create a pending result immediately
    monitor_result = MonitorResult(
        target_id=target_id,
        target_type=target_type,
        monitor_date=date.today(),
        status="pending",
    )
    db.add(monitor_result)
    await db.commit()
    await db.refresh(monitor_result)

    # Run the actual monitoring in the background
    background_tasks.add_task(execute_monitor, target_id, target_type)

    return {"status": "pending", "result_id": monitor_result.id}


@router.post("/sync/{target_id}")
async def sync_now(
    target_id: int,
    limit: int = Query(200, ge=1, le=10000),
    target_type: str = "social_media",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步账号：按指定条数拉取 X/微博/Facebook 正文存档（纯拉取，不 AI 摘要、不推送）。

    结果写入 monitor_results（summary 为空），返回 result_id 供前端展示/导出。
    Facebook 优先走 CDP 真实浏览器模拟人浏览（需 Chrome 登录 FB、CDP Proxy 运行），
    不可用时降级为 CSE 索引快照模式（约 10 条 Google 已索引的帖子）。
    """
    if target_type != "social_media":
        raise HTTPException(status_code=400, detail="同步仅支持社交账号")

    result = await db.execute(select(Target).where(Target.id == target_id, Target.user_id == user.id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    if target.platform not in ("x", "weibo", "facebook"):
        raise HTTPException(status_code=400, detail=f"同步暂不支持平台: {target.platform}（当前支持 x / weibo / facebook）")

    method = "opencli"
    if target.platform == "facebook":
        # Facebook 同步：优先 CDP 真实浏览器模拟人浏览（需 Chrome 登录 FB），
        # 降级 Google CSE 快照模式（headless Playwright）
        from services.monitor import crawl_with_fallback as _fb_fallback
        from crawlers.base import CrawlResult as _CrawlResult

        crawl_result, method, _err = await _fb_fallback(
            target.platform, target.account_name, target.account_url,
            post_limit=min(limit, 100),
        )
        if crawl_result is None:
            crawl_result = _CrawlResult(
                success=False,
                error_message="所有爬取方式均失败: " + ("; ".join(_err) or "未知错误"),
            )
    else:
        if not _check_opencli():
            raise HTTPException(status_code=503, detail="OpenCLI 未安装，请运行: npm install -g @jackwener/opencli")

        # 平台抓取上限：OpenCLI 微博 user-posts 最多 100 条，X tweets 最多 10000 条
        platform_limit = min(limit, 100 if target.platform == "weibo" else 10000)

        crawl_result = await crawl_with_opencli(
            target.platform, target.account_name, target.account_url, limit=platform_limit,
        )

    monitor_result = MonitorResult(
        target_id=target_id,
        target_type="social_media",
        monitor_date=date.today(),
    )
    if crawl_result.success:
        import json as _json
        monitor_result.status = "success"
        monitor_result.crawl_method = method or "opencli"
        monitor_result.raw_content = _json.dumps(
            [{
                "title": p.title,
                "content": p.content,
                "url": p.url,
                "likes": p.likes,
                "comments_count": p.comments_count,
                "shares": p.shares,
                "views": p.views,
                "images": p.images,
                "author_name": p.author_name,
                "author_avatar": p.author_avatar,
                "published_at": p.published_at.isoformat() if p.published_at else None,
            } for p in crawl_result.posts],
            ensure_ascii=False,
        )
        db.add(monitor_result)
        await db.commit()
        await db.refresh(monitor_result)
        return {
            "status": "success",
            "result_id": monitor_result.id,
            "posts_count": len(crawl_result.posts),
        }

    monitor_result.status = "failed"
    monitor_result.error_message = crawl_result.error_message or "同步失败"
    db.add(monitor_result)
    await db.commit()
    await db.refresh(monitor_result)
    return {
        "status": "failed",
        "result_id": monitor_result.id,
        "error_message": monitor_result.error_message,
    }
