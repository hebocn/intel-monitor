# intel-monitor/backend/routers/intelligence.py
"""战略情报报告 API 路由 — 包含分类管理和报告生成两个子模块。"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from auth import get_current_user
from database import get_db, async_session
from models.user import User
from models.intelligence_category import IntelligenceCategory, CATEGORY_SEEDS
from models.intelligence_report import IntelligenceReport
from schemas.intelligence import (
    CategoryCreate, CategoryUpdate, CategoryTree,
    ReportGenerateRequest, ReportProgressResponse, ReportDetailResponse,
    ReportListItem, ReportListResponse, GenerateResponse, ExportRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _seed_categories(db):
    """Insert preset category tree if table is empty."""
    existing = await db.execute(select(func.count(IntelligenceCategory.id)))
    if existing.scalar() > 0:
        return  # Already seeded

    created: list[IntelligenceCategory] = []
    for name, level, parent_index, sort_order in CATEGORY_SEEDS:
        parent_id = created[parent_index - 1].id if parent_index else None
        cat = IntelligenceCategory(
            name=name, level=level, parent_id=parent_id, sort_order=sort_order
        )
        db.add(cat)
        await db.flush()
        created.append(cat)
    await db.commit()
    logger.info(f"Seeded {len(created)} intelligence categories")


# ── Category APIs ───────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return category tree (nested JSON)."""
    await _seed_categories(db)
    result = await db.execute(
        select(IntelligenceCategory).order_by(IntelligenceCategory.sort_order)
    )
    all_cats = result.scalars().all()

    # Build tree in-memory (no lazy-load dependency on session)
    cat_map: dict[int, dict] = {}
    roots: list[dict] = []
    for cat in all_cats:
        node = {"id": cat.id, "name": cat.name, "level": cat.level, "sort_order": cat.sort_order, "children": []}
        cat_map[cat.id] = node
    for cat in all_cats:
        node = cat_map[cat.id]
        if cat.parent_id and cat.parent_id in cat_map:
            cat_map[cat.parent_id]["children"].append(node)
        elif cat.parent_id is None:
            roots.append(node)
    # Sort by sort_order
    for node in cat_map.values():
        node["children"].sort(key=lambda x: x["sort_order"])
    roots.sort(key=lambda x: x["sort_order"])
    return roots


@router.post("/categories")
async def create_category(
    req: CategoryCreate,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Create a new category node."""
    if req.parent_id is not None:
        parent = await db.get(IntelligenceCategory, req.parent_id)
        if not parent:
            raise HTTPException(404, "父分类不存在")

    cat = IntelligenceCategory(
        name=req.name, level=req.level,
        parent_id=req.parent_id, sort_order=req.sort_order,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "level": cat.level, "sort_order": cat.sort_order, "children": []}


@router.put("/categories/{cat_id}")
async def update_category(
    cat_id: int, req: CategoryUpdate,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    cat = await db.get(IntelligenceCategory, cat_id)
    if not cat:
        raise HTTPException(404, "分类不存在")
    if req.name is not None:
        cat.name = req.name
    if req.sort_order is not None:
        cat.sort_order = req.sort_order
    if req.is_active is not None:
        cat.is_active = req.is_active
    await db.commit()
    return {"id": cat.id, "name": cat.name, "level": cat.level, "sort_order": cat.sort_order, "children": [], "parent_id": cat.parent_id}


@router.delete("/categories/{cat_id}")
async def delete_category(
    cat_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    cat = await db.get(IntelligenceCategory, cat_id)
    if not cat:
        raise HTTPException(404, "分类不存在")
    # Check no reports reference this category
    report_count = await db.execute(
        select(func.count(IntelligenceReport.id)).where(
            IntelligenceReport.category_id == cat_id
        )
    )
    if report_count.scalar() > 0:
        raise HTTPException(400, "该分类下存在报告，无法删除。请先删除或移动关联报告。")
    # Check no children
    child_count = await db.execute(
        select(func.count(IntelligenceCategory.id)).where(
            IntelligenceCategory.parent_id == cat_id
        )
    )
    if child_count.scalar() > 0:
        raise HTTPException(400, "该分类下存在子分类，无法删除。请先删除子分类。")
    await db.delete(cat)
    await db.commit()
    return {"message": "分类已删除"}


# ── Report APIs ─────────────────────────────────────────────────────────────

@router.post("/reports/generate", response_model=GenerateResponse)
async def generate_report(
    req: ReportGenerateRequest,
    user: User = Depends(get_current_user),
):
    """Create a new intelligence report generation task. Runs async in background."""
    if req.category_id is not None:
        async with async_session() as db:
            cat = await db.get(IntelligenceCategory, req.category_id)
            if not cat:
                raise HTTPException(400, "分类不存在")

    title = req.title or f"战略情报报告 - {req.topic[:40]}..."

    async with async_session() as db:
        report = IntelligenceReport(
            user_id=user.id,
            title=title,
            topic=req.topic,
            category_id=req.category_id,
            search_platforms=json.dumps({
                "engines": req.search_engines,
                "crawlers": req.crawl_platforms,
            }, ensure_ascii=False),
            status="pending",
            progress_detail=json.dumps(
                {"phase": "init", "message": "任务已创建，等待启动..."},
                ensure_ascii=False,
            ),
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        # Await db session close before spawning async task
        report_id = report.id

    # Import services lazily to avoid circular imports
    from services.intelligence import run_report_generation
    asyncio.create_task(run_report_generation(
        report_id,
        req.topic,
        req.search_engines,
        req.crawl_platforms,
        req.max_search_results,
        req.max_sources,
        req.half_life_days,
    ))

    return GenerateResponse(
        report_id=report_id,
        status="pending",
        message=f"报告生成已启动：{req.topic[:60]}...",
    )


@router.get("/reports", response_model=ReportListResponse)
async def list_reports(
    status: str | None = Query(None),
    category_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(IntelligenceReport).where(IntelligenceReport.user_id == user.id)
    if status:
        stmt = stmt.where(IntelligenceReport.status == status)
    if category_id is not None:
        stmt = stmt.where(IntelligenceReport.category_id == category_id)
    stmt = stmt.order_by(IntelligenceReport.created_at.desc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    reports = (await db.execute(stmt)).scalars().all()

    return ReportListResponse(
        reports=[ReportListItem.model_validate(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(IntelligenceReport).where(
        IntelligenceReport.id == report_id,
        IntelligenceReport.user_id == user.id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "报告不存在")
    return ReportDetailResponse.model_validate(report)


@router.post("/reports/{report_id}/regenerate", response_model=GenerateResponse)
async def regenerate_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(IntelligenceReport).where(
        IntelligenceReport.id == report_id,
        IntelligenceReport.user_id == user.id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "报告不存在")

    # Reset status and progress
    report.status = "pending"
    report.progress_detail = json.dumps(
        {"phase": "init", "message": "重新生成中..."}, ensure_ascii=False
    )
    report.report_markdown = None
    report.sources_json = None
    report.error_log = None
    report.completed_at = None
    await db.commit()

    platforms_data = json.loads(report.search_platforms or "{}")
    engines = platforms_data.get("engines", ["firecrawl"])
    crawlers = platforms_data.get("crawlers", [])

    from services.intelligence import run_report_generation
    asyncio.create_task(run_report_generation(
        report_id, report.topic, engines, crawlers,
        # Use defaults for regenerate
    ))

    return GenerateResponse(
        report_id=report_id,
        status="pending",
        message=f"报告重新生成已启动",
    )


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    stmt = select(IntelligenceReport).where(
        IntelligenceReport.id == report_id,
        IntelligenceReport.user_id == user.id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "报告不存在")
    await db.delete(report)
    await db.commit()
    return {"message": "报告已删除"}


@router.post("/reports/{report_id}/export")
async def export_report(
    report_id: int,
    req: ExportRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """Export report as docx or pdf. Returns binary file."""
    stmt = select(IntelligenceReport).where(
        IntelligenceReport.id == report_id,
        IntelligenceReport.user_id == user.id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    if not report or not report.report_markdown:
        raise HTTPException(404, "报告不存在或尚未完成")

    from fastapi.responses import Response
    from urllib.parse import quote

    if req.format == "docx":
        from services.report_exporter import export_to_docx
        file_bytes = await export_to_docx(report.title, report.report_markdown)
        encoded_filename = quote(report.title + ".docx")
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
    else:  # pdf
        from services.report_exporter import export_to_pdf
        file_bytes = await export_to_pdf(report.title, report.report_markdown)
        encoded_filename = quote(report.title + ".pdf")
        return Response(
            content=file_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
