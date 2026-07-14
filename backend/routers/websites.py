# intel-monitor/backend/routers/websites.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.website import WebsiteTarget
from schemas.website import WebsiteCreate, WebsiteUpdate, WebsiteResponse

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
