from datetime import date

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
