# intel-monitor/backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from schemas.auth import SetupRequest, LoginRequest, TokenResponse, SetupStatusResponse, RegisterRequest, ResetPasswordRequest
from auth import get_password_hash, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status", response_model=SetupStatusResponse)
async def check_setup_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(User))
    count = result.scalar()
    return SetupStatusResponse(needs_setup=(count == 0))


@router.post("/setup", response_model=TokenResponse)
async def initial_setup(req: SetupRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(User))
    if result.scalar() > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setup already completed")

    user = User(username=req.username, password_hash=get_password_hash(req.password))
    db.add(user)
    await db.commit()

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse)
async def register_user(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(User))
    if result.scalar() == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先完成系统初始化")

    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    user = User(username=req.username, password_hash=get_password_hash(req.password))
    db.add(user)
    await db.commit()

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.password_hash = get_password_hash(req.new_password)
    await db.commit()
    return {"message": "密码已重置"}
