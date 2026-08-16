# intel-monitor/backend/routers/websites.py
import io

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.website import WebsiteTarget
from schemas.website import WebsiteCreate, WebsiteUpdate, WebsiteResponse
from services.importer import make_website_template, import_websites

router = APIRouter(prefix="/api/websites", tags=["websites"])


@router.get("", response_model=list[WebsiteResponse])
async def list_websites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebsiteTarget).where(WebsiteTarget.user_id == user.id).order_by(WebsiteTarget.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=WebsiteResponse, status_code=status.HTTP_201_CREATED)
async def create_website(
    req: WebsiteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    website = WebsiteTarget(user_id=user.id, **req.model_dump())
    db.add(website)
    await db.commit()
    await db.refresh(website)
    return website


@router.put("/{website_id}", response_model=WebsiteResponse)
async def update_website(
    website_id: int,
    req: WebsiteUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebsiteTarget).where(WebsiteTarget.id == website_id, WebsiteTarget.user_id == user.id)
    )
    website = result.scalar_one_or_none()
    if not website:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(website, field, value)
    await db.commit()
    await db.refresh(website)
    return website


@router.delete("/{website_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website(
    website_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WebsiteTarget).where(WebsiteTarget.id == website_id, WebsiteTarget.user_id == user.id)
    )
    website = result.scalar_one_or_none()
    if not website:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website not found")
    await db.delete(website)
    await db.commit()


# ── 批量导入 ─────────────────────────────────────────────

@router.get("/import/template")
async def download_website_template(user: User = Depends(get_current_user)):
    """下载网站批量导入模板（xlsx，列名固定：网站名称 / 网站URL）。"""
    content = make_website_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="website_import_template.xlsx"'},
    )


@router.post("/import")
async def import_websites_batch(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """批量导入网站（xlsx/xls/csv）。列名必须为：网站名称 / 网站URL。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        existing = (await db.execute(
            select(WebsiteTarget.url).where(WebsiteTarget.user_id == user.id)
        )).scalars().all()
        existing_urls = {u.lower().rstrip("/") for u in existing if u}

        result, items = import_websites(file.filename or "upload.xlsx", data, existing_urls)
        for item in items:
            db.add(WebsiteTarget(user_id=user.id, **item))
        await db.commit()

        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.exception("[import] 网站批量导入失败")
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")
