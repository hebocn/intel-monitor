# 情报监控平台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local intelligence monitoring platform that tracks social media accounts and websites, summarizes daily content via AI, and extracts top-10 hot comments.

**Architecture:** FastAPI single-process backend serving REST API + static React frontend. SQLite for storage. Playwright for CDP-based crawling. MiniMax API for content summarization. APScheduler for per-target cron scheduling.

**Tech Stack:** Python FastAPI, React + Ant Design + Vite, SQLite + SQLAlchemy, Playwright, MiniMax API, APScheduler, JWT auth

---

## File Map

```
intel-monitor/
├── backend/
│   ├── main.py                          # FastAPI app, startup, static mount
│   ├── config.py                        # Pydantic Settings from .env
│   ├── database.py                      # SQLAlchemy async engine + session
│   ├── auth.py                          # JWT token creation/verification
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                      # User model
│   │   ├── target.py                    # Social media target model
│   │   ├── website.py                   # Website target model
│   │   ├── result.py                    # MonitorResult model
│   │   └── comment.py                   # HotComment model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py                      # Auth request/response schemas
│   │   ├── target.py                    # Target schemas
│   │   ├── website.py                   # Website schemas
│   │   ├── result.py                    # Result schemas
│   │   └── dashboard.py                # Dashboard schemas
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py                      # /api/auth/* endpoints
│   │   ├── targets.py                   # /api/targets/* endpoints
│   │   ├── websites.py                  # /api/websites/* endpoints
│   │   ├── results.py                   # /api/results/* endpoints
│   │   └── dashboard.py                # /api/dashboard endpoint
│   ├── crawlers/
│   │   ├── __init__.py
│   │   ├── base.py                      # BaseCrawler ABC
│   │   ├── x_crawler.py                 # X (Twitter) crawler
│   │   ├── youtube_crawler.py           # YouTube crawler
│   │   ├── xiaohongshu_crawler.py       # XiaoHongShu crawler
│   │   ├── douyin_crawler.py            # Douyin crawler
│   │   └── website_crawler.py           # Generic website crawler
│   ├── services/
│   │   ├── __init__.py
│   │   ├── summarizer.py                # MiniMax API content summarizer
│   │   ├── scheduler.py                 # APScheduler management
│   │   └── monitor.py                   # Monitor execution orchestrator
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx                     # React entry point
│       ├── App.tsx                      # Router + Auth guard
│       ├── theme.ts                     # Dark theme config
│       ├── services/
│       │   └── api.ts                   # Axios instance + interceptors
│       ├── components/
│       │   ├── AppLayout.tsx            # Sidebar + Header layout
│       │   └── ProtectedRoute.tsx       # Auth route guard
│       └── pages/
│           ├── LoginPage.tsx            # First-time setup + login
│           ├── DashboardPage.tsx        # Overview dashboard
│           ├── SocialAccountsPage.tsx   # Social account CRUD
│           ├── WebsitesPage.tsx         # Website CRUD
│           ├── MonitorDetailPage.tsx    # Single target history
│           └── SettingsPage.tsx         # System settings
├── start.bat                            # One-click start script
└── .gitignore
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `intel-monitor/backend/requirements.txt`
- Create: `intel-monitor/backend/.env.example`
- Create: `intel-monitor/backend/config.py`
- Create: `intel-monitor/backend/database.py`
- Create: `intel-monitor/.gitignore`

- [ ] **Step 1: Create backend directory structure**

```bash
cd E:/Gary/hebo/claude_projects
mkdir -p intel-monitor/backend/models
mkdir -p intel-monitor/backend/schemas
mkdir -p intel-monitor/backend/routers
mkdir -p intel-monitor/backend/crawlers
mkdir -p intel-monitor/backend/services
mkdir -p intel-monitor/backend/data
mkdir -p intel-monitor/frontend/src
```

- [ ] **Step 2: Write requirements.txt**

```txt
# intel-monitor/backend/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
aiosqlite==0.20.0
playwright==1.48.0
apscheduler==3.10.4
httpx==0.27.0
bcrypt==4.2.0
python-jose[cryptography]==3.3.0
pydantic==2.9.0
pydantic-settings==2.5.0
python-dotenv==1.0.1
```

- [ ] **Step 3: Write .env.example**

```env
# intel-monitor/backend/.env.example
MINIMAX_API_KEY=your_minimax_api_key_here
JWT_SECRET=auto_generated_on_first_run
JWT_EXPIRE_MINUTES=1440
DATABASE_URL=sqlite+aiosqlite:///./data/intel_monitor.db
HOST=0.0.0.0
PORT=8000
```

- [ ] **Step 4: Write config.py**

```python
# intel-monitor/backend/config.py
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MINIMAX_API_KEY: str = ""
    JWT_SECRET: str = secrets.token_urlsafe(32)
    JWT_EXPIRE_MINUTES: int = 1440
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/intel_monitor.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure data directory exists
Path("data").mkdir(exist_ok=True)
```

- [ ] **Step 5: Write database.py**

```python
# intel-monitor/backend/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 6: Write .gitignore**

```gitignore
# intel-monitor/.gitignore
__pycache__/
*.pyc
.env
data/
node_modules/
dist/
.vite/
*.db
```

- [ ] **Step 7: Commit**

```bash
cd E:/Gary/hebo/claude_projects
git init intel-monitor
cd intel-monitor
git add -A
git commit -m "chore: scaffold project structure with config and database"
```

---

## Task 2: Database Models

**Files:**
- Create: `intel-monitor/backend/models/__init__.py`
- Create: `intel-monitor/backend/models/user.py`
- Create: `intel-monitor/backend/models/target.py`
- Create: `intel-monitor/backend/models/website.py`
- Create: `intel-monitor/backend/models/result.py`
- Create: `intel-monitor/backend/models/comment.py`

- [ ] **Step 1: Write models/__init__.py**

```python
# intel-monitor/backend/models/__init__.py
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from models.comment import HotComment

__all__ = ["User", "Target", "WebsiteTarget", "MonitorResult", "HotComment"]
```

- [ ] **Step 2: Write models/user.py**

```python
# intel-monitor/backend/models/user.py
from datetime import datetime
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 3: Write models/target.py**

```python
# intel-monitor/backend/models/target.py
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # x/youtube/xiaohongshu/douyin
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_url: Mapped[str] = mapped_column(String(500), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    monitor_hour: Mapped[int] = mapped_column(Integer, default=9)
    monitor_minute: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 4: Write models/website.py**

```python
# intel-monitor/backend/models/website.py
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class WebsiteTarget(Base):
    __tablename__ = "website_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    css_selector: Mapped[str | None] = mapped_column(String(200), nullable=True)
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    monitor_hour: Mapped[int] = mapped_column(Integer, default=9)
    monitor_minute: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 5: Write models/result.py**

```python
# intel-monitor/backend/models/result.py
from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy.orm import relationship

from database import Base


class MonitorResult(Base):
    __tablename__ = "monitor_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # social_media / website
    monitor_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # success/failed/pending
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    hot_comments = relationship("HotComment", backref="monitor_result", lazy="selectin")
```

- [ ] **Step 6: Write models/comment.py**

```python
# intel-monitor/backend/models/comment.py
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class HotComment(Base):
    __tablename__ = "hot_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_result_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitor_results.id"), nullable=False)
    post_url: Mapped[str] = mapped_column(String(500), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add all database models (User, Target, WebsiteTarget, MonitorResult, HotComment)"
```

---

## Task 3: Auth System (JWT + Endpoints)

**Files:**
- Create: `intel-monitor/backend/auth.py`
- Create: `intel-monitor/backend/schemas/__init__.py`
- Create: `intel-monitor/backend/schemas/auth.py`
- Create: `intel-monitor/backend/routers/__init__.py`
- Create: `intel-monitor/backend/routers/auth.py`

- [ ] **Step 1: Write auth.py (JWT utilities)**

```python
# intel-monitor/backend/auth.py
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [ ] **Step 2: Write schemas/__init__.py**

```python
# intel-monitor/backend/schemas/__init__.py
```

- [ ] **Step 3: Write schemas/auth.py**

```python
# intel-monitor/backend/schemas/auth.py
from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetupStatusResponse(BaseModel):
    needs_setup: bool
```

- [ ] **Step 4: Write routers/__init__.py**

```python
# intel-monitor/backend/routers/__init__.py
```

- [ ] **Step 5: Write routers/auth.py**

```python
# intel-monitor/backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from schemas.auth import SetupRequest, LoginRequest, TokenResponse, SetupStatusResponse
from auth import get_password_hash, verify_password, create_access_token

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(data={"sub": user.username})
    return TokenResponse(access_token=token)
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: add JWT auth system with setup/login endpoints"
```

---

## Task 4: Target & Website CRUD Endpoints

**Files:**
- Create: `intel-monitor/backend/schemas/target.py`
- Create: `intel-monitor/backend/schemas/website.py`
- Create: `intel-monitor/backend/routers/targets.py`
- Create: `intel-monitor/backend/routers/websites.py`

- [ ] **Step 1: Write schemas/target.py**

```python
# intel-monitor/backend/schemas/target.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TargetCreate(BaseModel):
    platform: str = Field(..., pattern="^(x|youtube|xiaohongshu|douyin)$")
    account_name: str = Field(..., min_length=1, max_length=100)
    account_url: str = Field(..., max_length=500)
    avatar_url: Optional[str] = None
    monitor_interval_minutes: int = Field(default=1440, ge=60)
    monitor_hour: int = Field(default=9, ge=0, le=23)
    monitor_minute: int = Field(default=0, ge=0, le=59)
    is_active: bool = True


class TargetUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_url: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    monitor_interval_minutes: Optional[int] = Field(None, ge=60)
    monitor_hour: Optional[int] = Field(None, ge=0, le=23)
    monitor_minute: Optional[int] = Field(None, ge=0, le=59)
    is_active: Optional[bool] = None


class TargetResponse(BaseModel):
    id: int
    platform: str
    account_name: str
    account_url: str
    avatar_url: Optional[str]
    monitor_interval_minutes: int
    monitor_hour: int
    monitor_minute: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Write schemas/website.py**

```python
# intel-monitor/backend/schemas/website.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class WebsiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., max_length=500)
    css_selector: Optional[str] = Field(None, max_length=200)
    monitor_interval_minutes: int = Field(default=1440, ge=60)
    monitor_hour: int = Field(default=9, ge=0, le=23)
    monitor_minute: int = Field(default=0, ge=0, le=59)
    is_active: bool = True


class WebsiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, max_length=500)
    css_selector: Optional[str] = Field(None, max_length=200)
    monitor_interval_minutes: Optional[int] = Field(None, ge=60)
    monitor_hour: Optional[int] = Field(None, ge=0, le=23)
    monitor_minute: Optional[int] = Field(None, ge=0, le=59)
    is_active: Optional[bool] = None


class WebsiteResponse(BaseModel):
    id: int
    name: str
    url: str
    css_selector: Optional[str]
    monitor_interval_minutes: int
    monitor_hour: int
    monitor_minute: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Write routers/targets.py**

```python
# intel-monitor/backend/routers/targets.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.target import Target
from schemas.target import TargetCreate, TargetUpdate, TargetResponse

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("", response_model=list[TargetResponse])
async def list_targets(
    platform: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Target).where(Target.user_id == user.id)
    if platform:
        query = query.where(Target.platform == platform)
    query = query.order_by(Target.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
async def create_target(
    req: TargetCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = Target(user_id=user.id, **req.model_dump())
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return target


@router.put("/{target_id}", response_model=TargetResponse)
async def update_target(
    target_id: int,
    req: TargetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(
    target_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Target).where(Target.id == target_id, Target.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    await db.delete(target)
    await db.commit()
```

- [ ] **Step 4: Write routers/websites.py**

```python
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
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add Target and Website CRUD endpoints with schemas"
```

---

## Task 5: Results & Dashboard Endpoints

**Files:**
- Create: `intel-monitor/backend/schemas/result.py`
- Create: `intel-monitor/backend/schemas/dashboard.py`
- Create: `intel-monitor/backend/routers/results.py`
- Create: `intel-monitor/backend/routers/dashboard.py`

- [ ] **Step 1: Write schemas/result.py**

```python
# intel-monitor/backend/schemas/result.py
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel


class HotCommentResponse(BaseModel):
    id: int
    post_url: str
    comment_text: str
    author: str
    likes_count: int
    rank: int

    model_config = {"from_attributes": True}


class ResultResponse(BaseModel):
    id: int
    target_id: int
    target_type: str
    monitor_date: date
    summary: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ResultDetailResponse(ResultResponse):
    raw_content: Optional[str]
    hot_comments: list[HotCommentResponse] = []
```

- [ ] **Step 2: Write schemas/dashboard.py**

```python
# intel-monitor/backend/schemas/dashboard.py
from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_targets: int
    active_targets: int
    total_websites: int
    today_results: int
    today_success: int
    today_failed: int


class RecentResultItem(BaseModel):
    id: int
    target_name: str
    platform: str
    target_type: str
    status: str
    summary: str | None
    monitor_date: str


class DashboardResponse(BaseModel):
    stats: DashboardStats
    recent_results: list[RecentResultItem]
```

- [ ] **Step 3: Write routers/results.py**

```python
# intel-monitor/backend/routers/results.py
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from auth import get_current_user
from models.user import User
from models.result import MonitorResult
from models.comment import HotComment
from schemas.result import ResultResponse, ResultDetailResponse, HotCommentResponse

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("", response_model=list[ResultResponse])
async def list_results(
    target_id: int | None = None,
    target_type: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(MonitorResult)
    if target_id:
        query = query.where(MonitorResult.target_id == target_id)
    if target_type:
        query = query.where(MonitorResult.target_type == target_type)
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
```

- [ ] **Step 4: Write routers/dashboard.py**

```python
# intel-monitor/backend/routers/dashboard.py
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from schemas.dashboard import DashboardStats, RecentResultItem, DashboardResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Target counts
    target_count = (await db.execute(
        select(func.count()).select_from(Target).where(Target.user_id == user.id)
    )).scalar()
    active_count = (await db.execute(
        select(func.count()).select_from(Target).where(Target.user_id == user.id, Target.is_active == True)
    )).scalar()
    website_count = (await db.execute(
        select(func.count()).select_from(WebsiteTarget).where(WebsiteTarget.user_id == user.id)
    )).scalar()

    # Today's results
    today = date.today()
    today_total = (await db.execute(
        select(func.count()).select_from(MonitorResult).where(MonitorResult.monitor_date == today)
    )).scalar()
    today_success = (await db.execute(
        select(func.count()).select_from(MonitorResult).where(
            MonitorResult.monitor_date == today, MonitorResult.status == "success"
        )
    )).scalar()
    today_failed = (await db.execute(
        select(func.count()).select_from(MonitorResult).where(
            MonitorResult.monitor_date == today, MonitorResult.status == "failed"
        )
    )).scalar()

    # Recent results (last 20)
    recent_query = (
        select(MonitorResult)
        .order_by(MonitorResult.created_at.desc())
        .limit(20)
    )
    recent_results_raw = (await db.execute(recent_query)).scalars().all()

    recent_results = []
    for r in recent_results_raw:
        recent_results.append(RecentResultItem(
            id=r.id,
            target_name=f"Target #{r.target_id}",
            platform=r.target_type,
            target_type=r.target_type,
            status=r.status,
            summary=r.summary[:100] if r.summary else None,
            monitor_date=str(r.monitor_date),
        ))

    return DashboardResponse(
        stats=DashboardStats(
            total_targets=target_count,
            active_targets=active_count,
            total_websites=website_count,
            today_results=today_total,
            today_success=today_success,
            today_failed=today_failed,
        ),
        recent_results=recent_results,
    )
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: add Results and Dashboard API endpoints"
```

---

## Task 6: FastAPI Main App

**Files:**
- Create: `intel-monitor/backend/main.py`

- [ ] **Step 1: Write main.py**

```python
# intel-monitor/backend/main.py
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db
from routers import auth, targets, websites, results, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Intel Monitor", lifespan=lifespan)

# Include routers
app.include_router(auth.router)
app.include_router(targets.router)
app.include_router(websites.router)
app.include_router(results.router)
app.include_router(dashboard.router)

# Serve frontend static files
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = frontend_dist / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))


if __name__ == "__main__":
    import uvicorn
    from config import settings
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add FastAPI main app with router registration and static file serving"
```

---

## Task 7: Crawler Base + Website Crawler

**Files:**
- Create: `intel-monitor/backend/crawlers/__init__.py`
- Create: `intel-monitor/backend/crawlers/base.py`
- Create: `intel-monitor/backend/crawlers/website_crawler.py`

- [ ] **Step 1: Write crawlers/__init__.py**

```python
# intel-monitor/backend/crawlers/__init__.py
from crawlers.base import BaseCrawler, CrawlResult, PostData, CommentData
from crawlers.x_crawler import XCrawler
from crawlers.youtube_crawler import YouTubeCrawler
from crawlers.xiaohongshu_crawler import XiaoHongShuCrawler
from crawlers.douyin_crawler import DouyinCrawler
from crawlers.website_crawler import WebsiteCrawler

CRAWLER_MAP = {
    "x": XCrawler,
    "youtube": YouTubeCrawler,
    "xiaohongshu": XiaoHongShuCrawler,
    "douyin": DouyinCrawler,
}

__all__ = [
    "BaseCrawler", "CrawlResult", "PostData", "CommentData",
    "XCrawler", "YouTubeCrawler", "XiaoHongShuCrawler", "DouyinCrawler",
    "WebsiteCrawler", "CRAWLER_MAP",
]
```

- [ ] **Step 2: Write crawlers/base.py**

```python
# intel-monitor/backend/crawlers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommentData:
    text: str
    author: str
    likes: int = 0
    url: str = ""


@dataclass
class PostData:
    url: str
    title: str = ""
    content: str = ""
    likes: int = 0
    comments_count: int = 0
    published_at: datetime | None = None
    comments: list[CommentData] = field(default_factory=list)


@dataclass
class CrawlResult:
    posts: list[PostData] = field(default_factory=list)
    raw_html: str = ""
    success: bool = True
    error_message: str = ""


class BaseCrawler(ABC):
    def __init__(self):
        self.browser = None
        self.page = None

    async def init_browser(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    @abstractmethod
    async def crawl(self, account_url: str) -> CrawlResult:
        pass

    @abstractmethod
    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        pass
```

- [ ] **Step 3: Write crawlers/website_crawler.py**

```python
# intel-monitor/backend/crawlers/website_crawler.py
from crawlers.base import BaseCrawler, CrawlResult, PostData


class WebsiteCrawler(BaseCrawler):
    async def crawl(self, url: str, css_selector: str | None = None) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(2000)

            if css_selector:
                content = await self.page.inner_text(css_selector)
            else:
                content = await self.page.inner_text("body")

            title = await self.page.title()

            return CrawlResult(
                posts=[PostData(url=url, title=title, content=content[:5000])],
                raw_html=content[:10000],
                success=True,
            )
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, post_url: str) -> list:
        return []
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: add crawler base class and website crawler"
```

---

## Task 8: X (Twitter) Crawler

**Files:**
- Create: `intel-monitor/backend/crawlers/x_crawler.py`

- [ ] **Step 1: Write x_crawler.py**

```python
# intel-monitor/backend/crawlers/x_crawler.py
import re
from datetime import datetime
from crawlers.base import BaseCrawler, CrawlResult, PostData, CommentData


class XCrawler(BaseCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load more tweets
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 800)")
                await self.page.wait_for_timeout(1500)

            # Extract tweets
            tweet_elements = await self.page.query_selector_all('article[data-testid="tweet"]')
            posts = []
            for el in tweet_elements[:10]:
                try:
                    text_el = await el.query_selector('[data-testid="tweetText"]')
                    text = await text_el.inner_text() if text_el else ""

                    # Get tweet link
                    link_el = await el.query_selector('a[href*="/status/"]')
                    href = await link_el.get_attribute("href") if link_el else ""
                    url = f"https://x.com{href}" if href else ""

                    # Get like count
                    like_el = await el.query_selector('[data-testid="like"] span')
                    likes_text = await like_el.inner_text() if like_el else "0"
                    likes = self._parse_count(likes_text)

                    if text:
                        posts.append(PostData(url=url, content=text, likes=likes))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(post_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            replies = await self.page.query_selector_all('article[data-testid="tweet"]')
            comments = []
            for reply in replies[:20]:
                try:
                    text_el = await reply.query_selector('[data-testid="tweetText"]')
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await reply.query_selector('[data-testid="User-Name"] span')
                    author = await author_el.inner_text() if author_el else "Unknown"

                    like_el = await reply.query_selector('[data-testid="like"] span')
                    likes_text = await like_el.inner_text() if like_el else "0"
                    likes = self._parse_count(likes_text)

                    if text:
                        comments.append(CommentData(text=text, author=author, likes=likes))
                except Exception:
                    continue

            comments.sort(key=lambda c: c.likes, reverse=True)
            return comments[:10]
        except Exception:
            return []
        finally:
            await self.close()

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.strip().replace(",", "")
        if "K" in text:
            return int(float(text.replace("K", "")) * 1000)
        if "M" in text:
            return int(float(text.replace("M", "")) * 1000000)
        try:
            return int(text)
        except ValueError:
            return 0
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add X (Twitter) crawler"
```

---

## Task 9: YouTube Crawler

**Files:**
- Create: `intel-monitor/backend/crawlers/youtube_crawler.py`

- [ ] **Step 1: Write youtube_crawler.py**

```python
# intel-monitor/backend/crawlers/youtube_crawler.py
from crawlers.base import BaseCrawler, CrawlResult, PostData, CommentData


class YouTubeCrawler(BaseCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            # Navigate to videos tab
            videos_url = account_url.rstrip("/") + "/videos"
            await self.page.goto(videos_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load more
            for _ in range(2):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await self.page.wait_for_timeout(1000)

            # Get video elements
            video_elements = await self.page.query_selector_all("ytd-rich-item-renderer")
            posts = []
            for el in video_elements[:10]:
                try:
                    title_el = await el.query_selector("#video-title")
                    title = await title_el.inner_text() if title_el else ""
                    href = await title_el.get_attribute("href") if title_el else ""
                    url = f"https://www.youtube.com{href}" if href else ""

                    views_el = await el.query_selector("#metadata-line span")
                    views = await views_el.inner_text() if views_el else ""

                    if title:
                        posts.append(PostData(url=url, title=title.strip(), content=views.strip()))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, video_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(video_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to comments section
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 500)")
                await self.page.wait_for_timeout(1000)

            comment_elements = await self.page.query_selector_all("ytd-comment-thread-renderer")
            comments = []
            for el in comment_elements[:20]:
                try:
                    text_el = await el.query_selector("#content-text")
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await el.query_selector("#author-text span")
                    author = await author_el.inner_text() if author_el else "Unknown"

                    likes_el = await el.query_selector("#vote-count-middle")
                    likes_text = await likes_el.inner_text() if likes_el else "0"
                    likes = self._parse_count(likes_text.strip())

                    if text:
                        comments.append(CommentData(text=text, author=author.strip(), likes=likes))
                except Exception:
                    continue

            comments.sort(key=lambda c: c.likes, reverse=True)
            return comments[:10]
        except Exception:
            return []
        finally:
            await self.close()

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").strip()
        if not text:
            return 0
        try:
            return int(text)
        except ValueError:
            return 0
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add YouTube crawler"
```

---

## Task 10: XiaoHongShu Crawler

**Files:**
- Create: `intel-monitor/backend/crawlers/xiaohongshu_crawler.py`

- [ ] **Step 1: Write xiaohongshu_crawler.py**

```python
# intel-monitor/backend/crawlers/xiaohongshu_crawler.py
from crawlers.base import BaseCrawler, CrawlResult, PostData, CommentData


class XiaoHongShuCrawler(BaseCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load notes
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await self.page.wait_for_timeout(1500)

            # Get note elements
            note_elements = await self.page.query_selector_all('section.note-item, div.note-item, a[href*="/explore/"]')
            posts = []
            for el in note_elements[:10]:
                try:
                    title_el = await el.query_selector('.title, .note-title, span')
                    title = await title_el.inner_text() if title_el else ""

                    href = await el.get_attribute("href") or ""
                    url = f"https://www.xiaohongshu.com{href}" if href.startswith("/") else href

                    if title and title.strip():
                        posts.append(PostData(url=url, title=title.strip()))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, note_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(note_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            comment_elements = await self.page.query_selector_all('.comment-item, div[class*="comment"]')
            comments = []
            for el in comment_elements[:20]:
                try:
                    text_el = await el.query_selector('.content, .comment-text, p')
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await el.query_selector('.author, .nickname, .name')
                    author = await author_el.inner_text() if author_el else "Unknown"

                    likes_el = await el.query_selector('.like-count, .likes, span[class*="like"]')
                    likes_text = await likes_el.inner_text() if likes_el else "0"
                    likes = self._parse_count(likes_text.strip())

                    if text:
                        comments.append(CommentData(text=text, author=author.strip(), likes=likes))
                except Exception:
                    continue

            comments.sort(key=lambda c: c.likes, reverse=True)
            return comments[:10]
        except Exception:
            return []
        finally:
            await self.close()

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").strip()
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add XiaoHongShu crawler"
```

---

## Task 11: Douyin Crawler

**Files:**
- Create: `intel-monitor/backend/crawlers/douyin_crawler.py`

- [ ] **Step 1: Write douyin_crawler.py**

```python
# intel-monitor/backend/crawlers/douyin_crawler.py
from crawlers.base import BaseCrawler, CrawlResult, PostData, CommentData


class DouyinCrawler(BaseCrawler):
    async def crawl(self, account_url: str) -> CrawlResult:
        try:
            await self.init_browser()
            await self.page.goto(account_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            # Scroll to load videos
            for _ in range(3):
                await self.page.evaluate("window.scrollBy(0, 600)")
                await self.page.wait_for_timeout(1500)

            # Get video elements
            video_elements = await self.page.query_selector_all('li[class*="item"], div[class*="video-card"], a[href*="/video/"]')
            posts = []
            for el in video_elements[:10]:
                try:
                    title_el = await el.query_selector('p, .title, span[class*="title"]')
                    title = await title_el.inner_text() if title_el else ""

                    href = await el.get_attribute("href") or ""
                    url = f"https://www.douyin.com{href}" if href.startswith("/") else href

                    if title and title.strip():
                        posts.append(PostData(url=url, title=title.strip()))
                except Exception:
                    continue

            return CrawlResult(posts=posts, success=True)
        except Exception as e:
            return CrawlResult(success=False, error_message=str(e))
        finally:
            await self.close()

    async def get_hot_comments(self, video_url: str) -> list[CommentData]:
        try:
            await self.init_browser()
            await self.page.goto(video_url, wait_until="networkidle", timeout=30000)
            await self.page.wait_for_timeout(3000)

            comment_elements = await self.page.query_selector_all('div[class*="comment"], li[class*="comment"]')
            comments = []
            for el in comment_elements[:20]:
                try:
                    text_el = await el.query_selector('span[class*="text"], p, .content')
                    text = await text_el.inner_text() if text_el else ""

                    author_el = await el.query_selector('span[class*="name"], .author, .nickname')
                    author = await author_el.inner_text() if author_el else "Unknown"

                    likes_el = await el.query_selector('span[class*="like"], .like-count')
                    likes_text = await likes_el.inner_text() if likes_el else "0"
                    likes = self._parse_count(likes_text.strip())

                    if text:
                        comments.append(CommentData(text=text, author=author.strip(), likes=likes))
                except Exception:
                    continue

            comments.sort(key=lambda c: c.likes, reverse=True)
            return comments[:10]
        except Exception:
            return []
        finally:
            await self.close()

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").strip()
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add Douyin crawler"
```

---

## Task 12: MiniMax AI Summarizer

**Files:**
- Create: `intel-monitor/backend/services/__init__.py`
- Create: `intel-monitor/backend/services/summarizer.py`

- [ ] **Step 1: Write services/__init__.py**

```python
# intel-monitor/backend/services/__init__.py
```

- [ ] **Step 2: Write services/summarizer.py**

```python
# intel-monitor/backend/services/summarizer.py
import httpx
from config import settings
from crawlers.base import PostData, CommentData


MINIMAX_API_URL = "https://api.minimax.chat/v1/text/chatcompletion_v2"


class ContentSummarizer:
    def __init__(self):
        self.api_key = settings.MINIMAX_API_KEY

    async def _call_minimax(self, system_prompt: str, user_prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                MINIMAX_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "MiniMax-Text-01",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def summarize_posts(self, platform: str, account_name: str, posts: list[PostData]) -> str:
        if not posts:
            return "今日无新内容发布。"

        posts_text = "\n".join(
            f"- [{p.title or '无标题'}] {p.content[:200]} (点赞: {p.likes})"
            for p in posts
        )

        system_prompt = (
            "你是一个情报分析助手。请对以下社交媒体账号今日发布的内容进行简洁总结。"
            "总结应包括：主要内容主题、发布数量、互动情况概述。"
            "使用中文回复，控制在200字以内。"
        )
        user_prompt = f"平台: {platform}\n账号: {account_name}\n今日发布内容:\n{posts_text}"

        try:
            return await self._call_minimax(system_prompt, user_prompt)
        except Exception as e:
            return f"总结生成失败: {str(e)}"

    async def summarize_website(self, site_name: str, content: str) -> str:
        if not content:
            return "今日无内容变化。"

        system_prompt = (
            "你是一个情报分析助手。请对以下网站的最新内容进行简洁总结。"
            "总结应包括：主要内容、关键信息点。"
            "使用中文回复，控制在200字以内。"
        )
        user_prompt = f"网站: {site_name}\n内容:\n{content[:3000]}"

        try:
            return await self._call_minimax(system_prompt, user_prompt)
        except Exception as e:
            return f"总结生成失败: {str(e)}"

    async def extract_hot_comments(
        self, all_comments: list[CommentData], max_count: int = 10
    ) -> list[CommentData]:
        if not all_comments:
            return []

        # Sort by likes and take top candidates
        sorted_comments = sorted(all_comments, key=lambda c: c.likes, reverse=True)
        candidates = sorted_comments[:max_count * 2]

        if len(candidates) <= max_count:
            return candidates[:max_count]

        comments_text = "\n".join(
            f"{i+1}. [{c.likes}赞] {c.author}: {c.text[:100]}"
            for i, c in enumerate(candidates)
        )

        system_prompt = (
            "从以下评论中选出最有价值、最热门的10条。"
            "按热度排序，返回编号列表，每行一个编号。"
            "只返回编号，如: 1,3,5,7,9,11,13,15,17,19"
        )

        try:
            result = await self._call_minimax(system_prompt, comments_text)
            indices = [int(x.strip()) - 1 for x in result.split(",") if x.strip().isdigit()]
            return [candidates[i] for i in indices if 0 <= i < len(candidates)][:max_count]
        except Exception:
            return candidates[:max_count]


summarizer = ContentSummarizer()
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: add MiniMax AI summarizer service"
```

---

## Task 13: Monitor Execution Orchestrator

**Files:**
- Create: `intel-monitor/backend/services/monitor.py`

- [ ] **Step 1: Write services/monitor.py**

```python
# intel-monitor/backend/services/monitor.py
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from models.comment import HotComment
from crawlers import CRAWLER_MAP, WebsiteCrawler
from services.summarizer import summarizer


async def execute_monitor(target_id: int, target_type: str = "social_media"):
    """Execute monitoring for a single target."""
    async with async_session() as db:
        if target_type == "social_media":
            result = await db.execute(select(Target).where(Target.id == target_id))
            target = result.scalar_one_or_none()
            if not target:
                return
            await _monitor_social_target(db, target)
        else:
            result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.id == target_id))
            target = result.scalar_one_or_none()
            if not target:
                return
            await _monitor_website_target(db, target)


async def _monitor_social_target(db: AsyncSession, target: Target):
    crawler_cls = CRAWLER_MAP.get(target.platform)
    if not crawler_cls:
        return

    monitor_result = MonitorResult(
        target_id=target.id,
        target_type="social_media",
        monitor_date=date.today(),
        status="pending",
    )
    db.add(monitor_result)
    await db.commit()
    await db.refresh(monitor_result)

    try:
        crawler = crawler_cls()
        crawl_result = await crawler.crawl(target.account_url)

        if not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = crawl_result.error_message
            await db.commit()
            return

        # Get hot comments for each post
        all_comments = []
        for post in crawl_result.posts:
            if post.url:
                try:
                    comments = await crawler.get_hot_comments(post.url)
                    post.comments = comments
                    all_comments.extend(comments)
                except Exception:
                    pass

        # Summarize
        summary = await summarizer.summarize_posts(target.platform, target.account_name, crawl_result.posts)
        hot = await summarizer.extract_hot_comments(all_comments)

        # Save results
        monitor_result.summary = summary
        monitor_result.raw_content = json.dumps(
            [{"title": p.title, "content": p.content, "url": p.url, "likes": p.likes} for p in crawl_result.posts],
            ensure_ascii=False,
        )
        monitor_result.status = "success"

        # Save hot comments
        for i, comment in enumerate(hot):
            db.add(HotComment(
                monitor_result_id=monitor_result.id,
                post_url=comment.url,
                comment_text=comment.text,
                author=comment.author,
                likes_count=comment.likes,
                rank=i + 1,
            ))

        await db.commit()

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        await db.commit()


async def _monitor_website_target(db: AsyncSession, target: WebsiteTarget):
    monitor_result = MonitorResult(
        target_id=target.id,
        target_type="website",
        monitor_date=date.today(),
        status="pending",
    )
    db.add(monitor_result)
    await db.commit()
    await db.refresh(monitor_result)

    try:
        crawler = WebsiteCrawler()
        crawl_result = await crawler.crawl(target.url, target.css_selector)

        if not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = crawl_result.error_message
            await db.commit()
            return

        content = crawl_result.posts[0].content if crawl_result.posts else ""
        summary = await summarizer.summarize_website(target.name, content)

        monitor_result.summary = summary
        monitor_result.raw_content = content[:10000]
        monitor_result.status = "success"
        await db.commit()

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        await db.commit()


async def monitor_all_active():
    """Run monitoring for all active targets (called by scheduler)."""
    async with async_session() as db:
        # Social media targets
        result = await db.execute(select(Target).where(Target.is_active == True))
        targets = result.scalars().all()
        for target in targets:
            try:
                await execute_monitor(target.id, "social_media")
            except Exception:
                pass

        # Website targets
        result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.is_active == True))
        websites = result.scalars().all()
        for website in websites:
            try:
                await execute_monitor(website.id, "website")
            except Exception:
                pass
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add monitor execution orchestrator"
```

---

## Task 14: APScheduler Integration

**Files:**
- Create: `intel-monitor/backend/services/scheduler.py`
- Create: `intel-monitor/backend/routers/schedule.py`

- [ ] **Step 1: Write services/scheduler.py**

```python
# intel-monitor/backend/services/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from services.monitor import execute_monitor
from sqlalchemy import select

scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Initialize the scheduler."""
    if not scheduler.running:
        scheduler.start()


async def refresh_jobs():
    """Reload all monitor jobs from database."""
    # Remove existing jobs
    scheduler.remove_all_jobs()

    async with async_session() as db:
        # Social media targets
        result = await db.execute(select(Target).where(Target.is_active == True))
        targets = result.scalars().all()
        for t in targets:
            scheduler.add_job(
                execute_monitor,
                trigger=CronTrigger(hour=t.monitor_hour, minute=t.monitor_minute),
                args=[t.id, "social_media"],
                id=f"target_{t.id}",
                replace_existing=True,
            )

        # Website targets
        result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.is_active == True))
        websites = result.scalars().all()
        for w in websites:
            scheduler.add_job(
                execute_monitor,
                trigger=CronTrigger(hour=w.monitor_hour, minute=w.monitor_minute),
                args=[w.id, "website"],
                id=f"website_{w.id}",
                replace_existing=True,
            )


def get_job_status() -> list[dict]:
    """Get status of all scheduled jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs
```

- [ ] **Step 2: Write routers/schedule.py**

```python
# intel-monitor/backend/routers/schedule.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from auth import get_current_user
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from services.scheduler import refresh_jobs, get_job_status
from services.monitor import execute_monitor

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/status")
async def schedule_status(user: User = Depends(get_current_user)):
    return {"jobs": get_job_status()}


@router.post("/refresh")
async def refresh_schedule(user: User = Depends(get_current_user)):
    await refresh_jobs()
    return {"message": "Schedule refreshed"}


@router.post("/run/{target_id}")
async def run_now(
    target_id: int,
    target_type: str = "social_media",
    user: User = Depends(get_current_user),
):
    try:
        await execute_monitor(target_id, target_type)
        return {"message": "Monitor executed"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
```

- [ ] **Step 3: Update main.py to include schedule router and startup scheduler**

Add to `main.py` after other router includes:

```python
from routers import schedule
from services.scheduler import setup_scheduler, refresh_jobs

app.include_router(schedule.router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    setup_scheduler()
    await refresh_jobs()
    yield
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: add APScheduler integration with dynamic job management"
```

---

## Task 15: Frontend Scaffolding

**Files:**
- Create: `intel-monitor/frontend/package.json`
- Create: `intel-monitor/frontend/vite.config.ts`
- Create: `intel-monitor/frontend/tsconfig.json`
- Create: `intel-monitor/frontend/index.html`
- Create: `intel-monitor/frontend/src/main.tsx`
- Create: `intel-monitor/frontend/src/App.tsx`
- Create: `intel-monitor/frontend/src/theme.ts`
- Create: `intel-monitor/frontend/src/services/api.ts`

- [ ] **Step 1: Write package.json**

```json
{
  "name": "intel-monitor-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "antd": "^5.20.0",
    "@ant-design/icons": "^5.4.0",
    "axios": "^1.7.4",
    "dayjs": "^1.11.12"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Write vite.config.ts**

```typescript
// intel-monitor/frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
```

- [ ] **Step 3: Write tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>情报监控平台</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

- [ ] **Step 5: Write theme.ts**

```typescript
// intel-monitor/frontend/src/theme.ts
import type { ThemeConfig } from 'antd'

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#667eea',
    colorBgContainer: '#1a1a2e',
    colorBgElevated: '#16213e',
    colorBgLayout: '#0f0f23',
    colorText: '#e0e0e0',
    colorTextSecondary: '#a0a0b0',
    colorBorder: '#2a2a4a',
    borderRadius: 8,
    fontSize: 14,
  },
  components: {
    Layout: {
      siderBg: '#0a0a1a',
      headerBg: '#0f0f23',
      bodyBg: '#0f0f23',
    },
    Menu: {
      darkBg: '#0a0a1a',
      darkItemColor: '#a0a0b0',
      darkItemSelectedBg: '#1a1a3e',
      darkItemSelectedColor: '#667eea',
    },
    Card: {
      colorBgContainer: '#1a1a2e',
    },
    Table: {
      colorBgContainer: '#1a1a2e',
      headerBg: '#16213e',
    },
    Input: {
      colorBgContainer: '#1a1a2e',
    },
    Select: {
      colorBgContainer: '#1a1a2e',
    },
    Modal: {
      contentBg: '#1a1a2e',
      headerBg: '#1a1a2e',
    },
  },
}

export default theme
```

- [ ] **Step 6: Write services/api.ts**

```typescript
// intel-monitor/frontend/src/services/api.ts
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Auth
export const authAPI = {
  checkStatus: () => api.get('/auth/status'),
  setup: (username: string, password: string) => api.post('/auth/setup', { username, password }),
  login: (username: string, password: string) => api.post('/auth/login', { username, password }),
}

// Targets
export const targetsAPI = {
  list: (platform?: string) => api.get('/targets', { params: { platform } }),
  create: (data: any) => api.post('/targets', data),
  update: (id: number, data: any) => api.put(`/targets/${id}`, data),
  delete: (id: number) => api.delete(`/targets/${id}`),
  runNow: (id: number) => api.post(`/targets/${id}/monitor`),
}

// Websites
export const websitesAPI = {
  list: () => api.get('/websites'),
  create: (data: any) => api.post('/websites', data),
  update: (id: number, data: any) => api.put(`/websites/${id}`, data),
  delete: (id: number) => api.delete(`/websites/${id}`),
}

// Results
export const resultsAPI = {
  list: (params: any) => api.get('/results', { params }),
  detail: (id: number) => api.get(`/results/${id}`),
}

// Dashboard
export const dashboardAPI = {
  get: () => api.get('/dashboard'),
}

// Schedule
export const scheduleAPI = {
  status: () => api.get('/schedule/status'),
  refresh: () => api.post('/schedule/refresh'),
  runNow: (targetId: number, targetType: string) =>
    api.post(`/schedule/run/${targetId}`, null, { params: { target_type: targetType } }),
}

export default api
```

- [ ] **Step 7: Write main.tsx**

```tsx
// intel-monitor/frontend/src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import theme from './theme'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider theme={theme} locale={zhCN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 8: Write App.tsx**

```tsx
// intel-monitor/frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import LoginPage from './pages/LoginPage'
import AppLayout from './components/AppLayout'
import DashboardPage from './pages/DashboardPage'
import SocialAccountsPage from './pages/SocialAccountsPage'
import WebsitesPage from './pages/WebsitesPage'
import MonitorDetailPage from './pages/MonitorDetailPage'
import SettingsPage from './pages/SettingsPage'
import { authAPI } from './services/api'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    setIsAuthenticated(!!token)
    setLoading(false)
  }, [])

  if (loading) return null

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={
          isAuthenticated ? <Navigate to="/" /> : <LoginPage onLogin={() => setIsAuthenticated(true)} />
        } />
        <Route path="/*" element={
          isAuthenticated ? (
            <AppLayout onLogout={() => { localStorage.removeItem('token'); setIsAuthenticated(false) }}>
              <Routes>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/social" element={<SocialAccountsPage />} />
                <Route path="/websites" element={<WebsitesPage />} />
                <Route path="/detail/:type/:id" element={<MonitorDetailPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Routes>
            </AppLayout>
          ) : <Navigate to="/login" />
        } />
      </Routes>
    </BrowserRouter>
  )
}

export default App
```

- [ ] **Step 9: Install dependencies and commit**

```bash
cd E:/Gary/hebo/claude_projects/intel-monitor/frontend
npm install
cd ..
git add -A
git commit -m "feat: scaffold React frontend with Vite, Ant Design, routing, and API service"
```

---

## Task 16: Login Page

**Files:**
- Create: `intel-monitor/frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Write LoginPage.tsx**

```tsx
// intel-monitor/frontend/src/pages/LoginPage.tsx
import { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, RadarChartOutlined } from '@ant-design/icons'
import { authAPI } from '../services/api'

const { Title, Text } = Typography

interface Props {
  onLogin: () => void
}

export default function LoginPage({ onLogin }: Props) {
  const [needsSetup, setNeedsSetup] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    authAPI.checkStatus().then(res => setNeedsSetup(res.data.needs_setup))
  }, [])

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = needsSetup
        ? await authAPI.setup(values.username, values.password)
        : await authAPI.login(values.username, values.password)
      localStorage.setItem('token', res.data.access_token)
      message.success(needsSetup ? '账号创建成功' : '登录成功')
      onLogin()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      background: 'linear-gradient(135deg, #0a0a1a 0%, #0f0f23 50%, #1a1a3e 100%)',
    }}>
      <Card style={{
        width: 400,
        background: 'rgba(26, 26, 46, 0.9)',
        border: '1px solid rgba(102, 126, 234, 0.3)',
        borderRadius: 16,
        boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <RadarChartOutlined style={{ fontSize: 48, color: '#667eea' }} />
          <Title level={3} style={{ color: '#e0e0e0', marginTop: 16, marginBottom: 4 }}>
            情报监控平台
          </Title>
          <Text style={{ color: '#a0a0b0' }}>
            {needsSetup ? '首次使用，请设置账号密码' : '请登录'}
          </Text>
        </div>

        <Form onFinish={onFinish} autoComplete="off">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }, { min: 4, message: '密码至少4位' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block size="large" loading={loading}
              style={{ background: 'linear-gradient(135deg, #667eea, #764ba2)', border: 'none' }}>
              {needsSetup ? '创建账号' : '登录'}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add login page with first-time setup support"
```

---

## Task 17: App Layout (Sidebar + Header)

**Files:**
- Create: `intel-monitor/frontend/src/components/AppLayout.tsx`
- Create: `intel-monitor/frontend/src/components/ProtectedRoute.tsx`

- [ ] **Step 1: Write AppLayout.tsx**

```tsx
// intel-monitor/frontend/src/components/AppLayout.tsx
import { Layout, Menu, Button, Typography, Avatar, Dropdown } from 'antd'
import {
  DashboardOutlined, MobileOutlined, GlobalOutlined,
  SettingOutlined, UserOutlined, LogoutOutlined, RadarChartOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation } from 'react-router-dom'
import { ReactNode } from 'react'

const { Sider, Header, Content } = Layout
const { Text } = Typography

interface Props {
  children: ReactNode
  onLogout: () => void
}

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/social', icon: <MobileOutlined />, label: '社交账号' },
  { key: '/websites', icon: <GlobalOutlined />, label: '网站监控' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

export default function AppLayout({ children, onLogout }: Props) {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} style={{ borderRight: '1px solid #2a2a4a' }}>
        <div style={{ padding: '20px 16px', display: 'flex', alignItems: 'center', gap: 10 }}>
          <RadarChartOutlined style={{ fontSize: 28, color: '#667eea' }} />
          <Text strong style={{ color: '#e0e0e0', fontSize: 16 }}>情报监控</Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ background: 'transparent', borderRight: 'none' }}
        />
      </Sider>

      <Layout>
        <Header style={{
          display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
          padding: '0 24px', borderBottom: '1px solid #2a2a4a',
        }}>
          <Dropdown menu={{
            items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: onLogout }],
          }}>
            <Button type="text" style={{ color: '#a0a0b0' }}>
              <Avatar size="small" icon={<UserOutlined />} style={{ background: '#667eea', marginRight: 8 }} />
              管理员
            </Button>
          </Dropdown>
        </Header>

        <Content style={{ padding: 24, overflow: 'auto' }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  )
}
```

- [ ] **Step 2: Write ProtectedRoute.tsx**

```tsx
// intel-monitor/frontend/src/components/ProtectedRoute.tsx
import { Navigate } from 'react-router-dom'
import { ReactNode } from 'react'

interface Props {
  children: ReactNode
}

export default function ProtectedRoute({ children }: Props) {
  const token = localStorage.getItem('token')
  if (!token) return <Navigate to="/login" />
  return <>{children}</>
}
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: add app layout with sidebar navigation and header"
```

---

## Task 18: Dashboard Page

**Files:**
- Create: `intel-monitor/frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Write DashboardPage.tsx**

```tsx
// intel-monitor/frontend/src/pages/DashboardPage.tsx
import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Table, Tag, Typography, Spin } from 'antd'
import {
  MobileOutlined, GlobalOutlined, CheckCircleOutlined,
  CloseCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import { dashboardAPI } from '../services/api'

const { Title } = Typography

export default function DashboardPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    dashboardAPI.get().then(res => setData(res.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  if (!data) return null

  const { stats, recent_results } = data

  const columns = [
    { title: '目标', dataIndex: 'target_name', key: 'target_name' },
    {
      title: '类型', dataIndex: 'target_type', key: 'target_type',
      render: (t: string) => t === 'social_media' ? <Tag color="blue">社交</Tag> : <Tag color="green">网站</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => {
        const map: Record<string, { color: string; icon: React.ReactNode }> = {
          success: { color: 'success', icon: <CheckCircleOutlined /> },
          failed: { color: 'error', icon: <CloseCircleOutlined /> },
          pending: { color: 'processing', icon: <ClockCircleOutlined /> },
        }
        const item = map[s] || map.pending
        return <Tag color={item.color} icon={item.icon}>{s}</Tag>
      },
    },
    { title: '总结', dataIndex: 'summary', key: 'summary', ellipsis: true },
    { title: '日期', dataIndex: 'monitor_date', key: 'monitor_date' },
  ]

  return (
    <div>
      <Title level={4} style={{ color: '#e0e0e0', marginBottom: 24 }}>仪表盘</Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col span={4}>
          <Card><Statistic title="监控目标" value={stats.total_targets} prefix={<MobileOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="活跃目标" value={stats.active_targets} valueStyle={{ color: '#667eea' }} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="网站监控" value={stats.total_websites} prefix={<GlobalOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="今日监控" value={stats.today_results} prefix={<ClockCircleOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="成功" value={stats.today_success} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col span={4}>
          <Card><Statistic title="失败" value={stats.today_failed} valueStyle={{ color: '#ff4d4f' }} prefix={<CloseCircleOutlined />} /></Card>
        </Col>
      </Row>

      <Card title="最近监控结果">
        <Table
          columns={columns}
          dataSource={recent_results}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add dashboard page with stats and recent results table"
```

---

## Task 19: Social Accounts Page

**Files:**
- Create: `intel-monitor/frontend/src/pages/SocialAccountsPage.tsx`

- [ ] **Step 1: Write SocialAccountsPage.tsx**

```tsx
// intel-monitor/frontend/src/pages/SocialAccountsPage.tsx
import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, Select, InputNumber, Switch, Tag, Space, message, Popconfirm, Typography } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { targetsAPI } from '../services/api'
import { useNavigate } from 'react-router-dom'

const { Title } = Typography

const platformOptions = [
  { value: 'x', label: 'X (Twitter)', color: '#1DA1F2' },
  { value: 'youtube', label: 'YouTube', color: '#FF0000' },
  { value: 'xiaohongshu', label: '小红书', color: '#FE2C55' },
  { value: 'douyin', label: '抖音', color: '#000000' },
]

const platformMap = Object.fromEntries(platformOptions.map(p => [p.value, p]))

export default function SocialAccountsPage() {
  const [targets, setTargets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTarget, setEditingTarget] = useState<any>(null)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const fetchTargets = async () => {
    setLoading(true)
    try {
      const res = await targetsAPI.list()
      setTargets(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchTargets() }, [])

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editingTarget) {
        await targetsAPI.update(editingTarget.id, values)
        message.success('更新成功')
      } else {
        await targetsAPI.create(values)
        message.success('添加成功')
      }
      setModalOpen(false)
      form.resetFields()
      setEditingTarget(null)
      fetchTargets()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    await targetsAPI.delete(id)
    message.success('删除成功')
    fetchTargets()
  }

  const handleRunNow = async (id: number) => {
    message.info('开始监控...')
    try {
      await targetsAPI.runNow(id)
      message.success('监控完成')
    } catch {
      message.error('监控失败')
    }
  }

  const columns = [
    {
      title: '平台', dataIndex: 'platform', key: 'platform',
      render: (p: string) => {
        const plat = platformMap[p]
        return <Tag color={plat?.color}>{plat?.label || p}</Tag>
      },
    },
    { title: '账号名称', dataIndex: 'account_name', key: 'account_name' },
    { title: '账号 URL', dataIndex: 'account_url', key: 'account_url', ellipsis: true },
    {
      title: '监控时间', key: 'schedule',
      render: (_: any, r: any) => `${String(r.monitor_hour).padStart(2, '0')}:${String(r.monitor_minute).padStart(2, '0')}`,
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active',
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => handleRunNow(record.id)}>执行</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingTarget(record)
            form.setFieldsValue(record)
            setModalOpen(true)
          }}>编辑</Button>
          <Button size="small" onClick={() => navigate(`/detail/social/${record.id}`)}>详情</Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: '#e0e0e0', margin: 0 }}>社交账号管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingTarget(null); form.resetFields(); setModalOpen(true) }}>
          添加账号
        </Button>
      </div>

      <Card>
        <Table columns={columns} dataSource={targets} rowKey="id" loading={loading} />
      </Card>

      <Modal
        title={editingTarget ? '编辑账号' : '添加账号'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditingTarget(null); form.resetFields() }}
        width={500}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="platform" label="平台" rules={[{ required: true }]}>
            <Select options={platformOptions} placeholder="选择平台" />
          </Form.Item>
          <Form.Item name="account_name" label="账号名称" rules={[{ required: true }]}>
            <Input placeholder="如: @elonmusk" />
          </Form.Item>
          <Form.Item name="account_url" label="账号 URL" rules={[{ required: true }]}>
            <Input placeholder="如: https://x.com/elonmusk" />
          </Form.Item>
          <Form.Item name="avatar_url" label="头像 URL">
            <Input placeholder="可选" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="monitor_hour" label="监控小时" initialValue={9}>
              <InputNumber min={0} max={23} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="monitor_minute" label="监控分钟" initialValue={0}>
              <InputNumber min={0} max={59} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add social accounts management page with CRUD and run-now"
```

---

## Task 20: Websites Page

**Files:**
- Create: `intel-monitor/frontend/src/pages/WebsitesPage.tsx`

- [ ] **Step 1: Write WebsitesPage.tsx**

```tsx
// intel-monitor/frontend/src/pages/WebsitesPage.tsx
import { useEffect, useState } from 'react'
import { Card, Table, Button, Modal, Form, Input, InputNumber, Switch, Tag, Space, message, Popconfirm, Typography } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { websitesAPI } from '../services/api'
import { useNavigate } from 'react-router-dom'

const { Title } = Typography

export default function WebsitesPage() {
  const [websites, setWebsites] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()
  const navigate = useNavigate()

  const fetch = async () => {
    setLoading(true)
    try {
      const res = await websitesAPI.list()
      setWebsites(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch() }, [])

  const handleSubmit = async () => {
    const values = await form.validateFields()
    try {
      if (editing) {
        await websitesAPI.update(editing.id, values)
        message.success('更新成功')
      } else {
        await websitesAPI.create(values)
        message.success('添加成功')
      }
      setModalOpen(false)
      form.resetFields()
      setEditing(null)
      fetch()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = async (id: number) => {
    await websitesAPI.delete(id)
    message.success('删除成功')
    fetch()
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: 'URL', dataIndex: 'url', key: 'url', ellipsis: true },
    { title: 'CSS 选择器', dataIndex: 'css_selector', key: 'css_selector', ellipsis: true },
    {
      title: '监控时间', key: 'schedule',
      render: (_: any, r: any) => `${String(r.monitor_hour).padStart(2, '0')}:${String(r.monitor_minute).padStart(2, '0')}`,
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active',
      render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => {
            websitesAPI.update(record.id, {}).then(() => message.info('已触发监控'))
          }}>执行</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditing(record)
            form.setFieldsValue(record)
            setModalOpen(true)
          }}>编辑</Button>
          <Button size="small" onClick={() => navigate(`/detail/website/${record.id}`)}>详情</Button>
          <Popconfirm title="确定删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ color: '#e0e0e0', margin: 0 }}>网站监控管理</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setModalOpen(true) }}>
          添加网站
        </Button>
      </div>

      <Card>
        <Table columns={columns} dataSource={websites} rowKey="id" loading={loading} />
      </Card>

      <Modal
        title={editing ? '编辑网站' : '添加网站'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); setEditing(null); form.resetFields() }}
        width={500}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="网站名称" rules={[{ required: true }]}>
            <Input placeholder="如: 某某新闻网" />
          </Form.Item>
          <Form.Item name="url" label="网站 URL" rules={[{ required: true }]}>
            <Input placeholder="https://example.com" />
          </Form.Item>
          <Form.Item name="css_selector" label="CSS 选择器 (可选)">
            <Input placeholder="如: .article-content" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="monitor_hour" label="监控小时" initialValue={9}>
              <InputNumber min={0} max={23} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="monitor_minute" label="监控分钟" initialValue={0}>
              <InputNumber min={0} max={59} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add website monitoring management page"
```

---

## Task 21: Monitor Detail Page

**Files:**
- Create: `intel-monitor/frontend/src/pages/MonitorDetailPage.tsx`

- [ ] **Step 1: Write MonitorDetailPage.tsx**

```tsx
// intel-monitor/frontend/src/pages/MonitorDetailPage.tsx
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Table, Tag, Typography, Descriptions, Empty, Spin, Collapse } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { resultsAPI } from '../services/api'

const { Title, Paragraph, Text } = Typography

export default function MonitorDetailPage() {
  const { type, id } = useParams<{ type: string; id: string }>()
  const [results, setResults] = useState<any[]>([])
  const [selectedResult, setSelectedResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    resultsAPI.list({ target_id: Number(id), target_type: type })
      .then(res => setResults(res.data))
      .finally(() => setLoading(false))
  }, [id, type])

  const loadDetail = async (resultId: number) => {
    const res = await resultsAPI.detail(resultId)
    setSelectedResult(res.data)
  }

  const resultColumns = [
    { title: '日期', dataIndex: 'monitor_date', key: 'monitor_date' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => {
        const map: Record<string, any> = {
          success: { color: 'success', icon: <CheckCircleOutlined />, text: '成功' },
          failed: { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
          pending: { color: 'processing', icon: <ClockCircleOutlined />, text: '进行中' },
        }
        const item = map[s] || map.pending
        return <Tag color={item.color} icon={item.icon}>{item.text}</Tag>
      },
    },
    { title: '总结', dataIndex: 'summary', key: 'summary', ellipsis: true },
    {
      title: '操作', key: 'actions',
      render: (_: any, record: any) => (
        <a onClick={() => loadDetail(record.id)}>查看详情</a>
      ),
    },
  ]

  const commentColumns = [
    { title: '排名', dataIndex: 'rank', key: 'rank', width: 60 },
    { title: '作者', dataIndex: 'author', key: 'author', width: 120 },
    { title: '评论内容', dataIndex: 'comment_text', key: 'comment_text', ellipsis: true },
    { title: '点赞', dataIndex: 'likes_count', key: 'likes_count', width: 80 },
    { title: '来源', dataIndex: 'post_url', key: 'post_url', ellipsis: true },
  ]

  return (
    <div>
      <Title level={4} style={{ color: '#e0e0e0', marginBottom: 24 }}>
        监控详情 - {type === 'social_media' ? '社交账号' : '网站'} #{id}
      </Title>

      <Card title="监控记录" style={{ marginBottom: 16 }}>
        <Table
          columns={resultColumns}
          dataSource={results}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          size="small"
        />
      </Card>

      {selectedResult && (
        <Card title={`监控结果详情 (${selectedResult.monitor_date})`}>
          <Descriptions column={2} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="状态">
              <Tag color={selectedResult.status === 'success' ? 'success' : 'error'}>
                {selectedResult.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="日期">{selectedResult.monitor_date}</Descriptions.Item>
          </Descriptions>

          {selectedResult.summary && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ color: '#e0e0e0' }}>AI 总结:</Text>
              <Paragraph style={{ color: '#a0a0b0', marginTop: 8 }}>{selectedResult.summary}</Paragraph>
            </div>
          )}

          {selectedResult.hot_comments?.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ color: '#e0e0e0' }}>热门评论 Top 10:</Text>
              <Table
                columns={commentColumns}
                dataSource={selectedResult.hot_comments}
                rowKey="id"
                pagination={false}
                size="small"
                style={{ marginTop: 8 }}
              />
            </div>
          )}

          {selectedResult.error_message && (
            <div>
              <Text strong style={{ color: '#ff4d4f' }}>错误信息:</Text>
              <Paragraph style={{ color: '#ff4d4f', marginTop: 8 }}>{selectedResult.error_message}</Paragraph>
            </div>
          )}
        </Card>
      )}

      {!selectedResult && results.length > 0 && (
        <Empty description="点击上方记录查看详情" />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add monitor detail page with history and hot comments"
```

---

## Task 22: Settings Page

**Files:**
- Create: `intel-monitor/frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Write SettingsPage.tsx**

```tsx
// intel-monitor/frontend/src/pages/SettingsPage.tsx
import { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Typography, message, Divider, List, Tag } from 'antd'
import { SaveOutlined, SyncOutlined } from '@ant-design/icons'
import { scheduleAPI } from '../services/api'

const { Title, Text } = Typography

export default function SettingsPage() {
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchJobs = async () => {
    try {
      const res = await scheduleAPI.status()
      setJobs(res.data.jobs)
    } catch {}
  }

  useEffect(() => { fetchJobs() }, [])

  const handleRefresh = async () => {
    setLoading(true)
    try {
      await scheduleAPI.refresh()
      message.success('调度已刷新')
      fetchJobs()
    } catch {
      message.error('刷新失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <Title level={4} style={{ color: '#e0e0e0', marginBottom: 24 }}>系统设置</Title>

      <Card title="调度任务" style={{ marginBottom: 16 }}>
        <div style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<SyncOutlined />} onClick={handleRefresh} loading={loading}>
            刷新调度
          </Button>
        </div>
        <List
          dataSource={jobs}
          locale={{ emptyText: '暂无调度任务' }}
          renderItem={(job: any) => (
            <List.Item>
              <List.Item.Meta
                title={<Text style={{ color: '#e0e0e0' }}>{job.id}</Text>}
                description={
                  <div>
                    <Text style={{ color: '#a0a0b0' }}>触发器: {job.trigger}</Text>
                    <br />
                    <Text style={{ color: '#a0a0b0' }}>
                      下次执行: {job.next_run || '未安排'}
                    </Text>
                  </div>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title="MiniMax API 配置">
        <Form layout="vertical">
          <Form.Item label="API Key">
            <Input.Password placeholder="MiniMax API Key" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" icon={<SaveOutlined />}>保存</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "feat: add settings page with scheduler status and API config"
```

---

## Task 23: Start Script & Integration

**Files:**
- Create: `intel-monitor/start.bat`
- Create: `intel-monitor/frontend/src/vite-env.d.ts`

- [ ] **Step 1: Write start.bat**

```bat
@echo off
echo ============================
echo  情报监控平台 - 启动
echo ============================
echo.

:: Build frontend if dist doesn't exist
if not exist "frontend\dist" (
    echo [1/3] Building frontend...
    cd frontend
    call npm run build
    cd ..
    echo.
)

:: Start backend
echo [2/3] Starting backend server...
cd backend
start /B python main.py
cd ..

echo.
echo [3/3] Server starting at http://localhost:8000
echo Press Ctrl+C to stop.
echo.
pause
```

- [ ] **Step 2: Write vite-env.d.ts**

```typescript
// intel-monitor/frontend/src/vite-env.d.ts
/// <reference types="vite/client" />
```

- [ ] **Step 3: Build frontend and test**

```bash
cd E:/Gary/hebo/claude_projects/intel-monitor/frontend
npm run build
```

- [ ] **Step 4: Install backend dependencies and test**

```bash
cd E:/Gary/hebo/claude_projects/intel-monitor/backend
pip install -r requirements.txt
playwright install chromium
```

- [ ] **Step 5: Commit**

```bash
cd E:/Gary/hebo/claude_projects/intel-monitor
git add -A
git commit -m "feat: add start script and final integration setup"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Project scaffolding | 6 |
| 2 | Database models | 6 |
| 3 | Auth system | 5 |
| 4 | Target & Website CRUD | 4 |
| 5 | Results & Dashboard | 4 |
| 6 | FastAPI main app | 1 |
| 7 | Crawler base + website | 3 |
| 8 | X crawler | 1 |
| 9 | YouTube crawler | 1 |
| 10 | XiaoHongShu crawler | 1 |
| 11 | Douyin crawler | 1 |
| 12 | MiniMax summarizer | 2 |
| 13 | Monitor orchestrator | 1 |
| 14 | APScheduler integration | 3 |
| 15 | Frontend scaffolding | 8 |
| 16 | Login page | 1 |
| 17 | App layout | 2 |
| 18 | Dashboard page | 1 |
| 19 | Social accounts page | 1 |
| 20 | Websites page | 1 |
| 21 | Monitor detail page | 1 |
| 22 | Settings page | 1 |
| 23 | Start script & integration | 2 |

**Total: 23 tasks, ~57 files**
