# Intel Monitor — 监控体验优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复监控状态显示、实现爬取降级链路、增强调度和筛选能力、改善登录错误反馈

**Architecture:** 6 个独立改动按优先级排列，每个可单独验证。核心改动在 monitor.py 的爬取逻辑（降级链路），后续任务依赖它。

**Tech Stack:** Python/FastAPI, SQLAlchemy async, APScheduler, React 18, Ant Design 5, Vite, axios

---

## File Structure

### 修改的文件

| 文件 | 改动内容 |
|------|----------|
| `backend/models/target.py` | 新增 `cron_schedule`, `post_limit`, `post_time_range_days`, `opencli_ready`, `last_verify_status`, `last_verify_method` 字段 |
| `backend/models/result.py` | 新增 `crawl_method` 字段 |
| `backend/schemas/target.py` | 新增字段的 schema 定义 |
| `backend/services/monitor.py` | 新增 `crawl_with_fallback()`，重构 `_monitor_social_target()` |
| `backend/services/scheduler.py` | 支持解析 `cron_schedule` 多表达式 |
| `backend/routers/schedule.py` | `run_now` 改为异步返回 pending result_id |
| `backend/routers/targets.py` | 创建 target 后触发异步预热验证 |
| `backend/crawlers/base.py` | 新增 `filter_posts()` 工具函数 |
| `backend/crawlers/opencli_crawler.py` | 适配 `post_limit` 参数 |
| `frontend/src/services/api.ts` | 新增 `resultsAPI.detail` 轮询支持 |
| `frontend/src/pages/SocialAccountsPage.tsx` | 乐观 UI + 轮询 + cron 模式 + 贴文参数表单 + 验证状态 |
| `frontend/src/pages/DashboardPage.tsx` | pending 状态轮询 |
| `frontend/src/pages/LoginPage.tsx` | 改进错误提示中文文案 |
| `frontend/src/pages/SettingsPage.tsx` | 调度任务分组显示 |

---

## Task 1: 状态显示修复 — 后端异步执行

**Files:**
- Modify: `backend/routers/schedule.py`

- [ ] **Step 1: 修改 `run_now` 端点为异步返回**

将 `backend/routers/schedule.py` 的 `run_now` 函数改为：收到请求后立即创建 MonitorResult（status="pending"），返回 `{status: "pending", result_id}`，然后后台异步执行爬取。

```python
# intel-monitor/backend/routers/schedule.py
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from auth import get_current_user
from models.user import User
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
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
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Create a pending result immediately
    from datetime import date
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
```

- [ ] **Step 2: 验证后端改动**

启动后端，调用 `POST /api/schedule/run/1?target_type=social_media`，确认：
- 立即返回 `{"status": "pending", "result_id": N}`
- 数据库中出现一条 status="pending" 的 MonitorResult
- 后台爬取完成后，该记录的 status 更新为 success/failed

---

## Task 2: 状态显示修复 — 前端轮询

**Files:**
- Modify: `frontend/src/pages/SocialAccountsPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: 修改 SocialAccountsPage 的 `handleRunNow`**

将 `frontend/src/pages/SocialAccountsPage.tsx` 中的 `handleRunNow` 改为乐观 UI + 轮询模式：

```tsx
const handleRunNow = async (id: number) => {
  setRunningId(id)
  message.info('开始监测...')
  try {
    const res = await scheduleAPI.runNow(id, 'social_media')
    const { result_id } = res.data

    // Poll for result completion
    const pollResult = async () => {
      for (let i = 0; i < 60; i++) {  // max 2 minutes
        await new Promise(r => setTimeout(r, 2000))
        try {
          const detailRes = await resultsAPI.detail(result_id)
          const result = detailRes.data
          if (result.status === 'success') {
            message.success('监测完成')
            fetchTargets()
            return
          } else if (result.status === 'failed') {
            message.warning(result.error_message || '监测失败')
            fetchTargets()
            return
          }
          // still pending, continue polling
        } catch {}
      }
      // timeout - refresh anyway
      fetchTargets()
    }
    pollResult()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '监测启动失败')
    setRunningId(null)
  }
}
```

需要在文件顶部确认 `resultsAPI` 已导入（当前只导入了 `targetsAPI, scheduleAPI`）：

```tsx
import { targetsAPI, scheduleAPI, resultsAPI } from '../services/api'
```

- [ ] **Step 2: 修改 DashboardPage 支持 pending 轮询**

在 `frontend/src/pages/DashboardPage.tsx` 中，检查 `recent_results` 是否有 pending 状态的记录，如果有则启动轮询：

在 `fetchData` 函数后添加 effect：

```tsx
// Auto-poll if there are pending results
useEffect(() => {
  if (!data?.recent_results) return
  const hasPending = data.recent_results.some((r: any) => r.status === 'pending')
  if (!hasPending) return

  const timer = setInterval(() => {
    fetchData()
  }, 3000)

  return () => clearInterval(timer)
}, [data])
```

- [ ] **Step 3: 验证前端改动**

1. 点击"执行"按钮，确认：
   - 按钮立即显示"执行中"loading 状态
   - 不再出现短暂"监测失败"闪现
   - 爬取完成后弹出成功/失败提示
2. 在有 pending 结果时打开仪表盘，确认：
   - pending 状态显示为"进行中"蓝色标签
   - 自动刷新直到状态变更

---

## Task 3: 登录错误提示优化

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`
- Modify: `backend/routers/auth.py`

- [ ] **Step 1: 改进后端错误信息为中文**

修改 `backend/routers/auth.py` 第 40 行：

```python
# Before
raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

# After
raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
```

- [ ] **Step 2: 改进前端错误处理**

修改 `frontend/src/pages/LoginPage.tsx` 的 catch 块，增加更细致的错误分类：

```tsx
// Before (line 32-34)
catch (err: any) {
  message.error(err.response?.data?.detail || '操作失败')
}

// After
catch (err: any) {
  if (err.response?.status === 401) {
    message.error(err.response.data?.detail || '用户名或密码错误')
  } else if (err.response?.status === 422) {
    message.error('请输入用户名和密码')
  } else if (!err.response) {
    message.error('网络连接失败，请检查服务是否运行')
  } else {
    message.error(err.response?.data?.detail || '登录失败，请稍后重试')
  }
}
```

- [ ] **Step 3: 验证**

1. 输入错误密码登录，确认显示"用户名或密码错误"
2. 停止后端服务，尝试登录，确认显示"网络连接失败"

---

## Task 4: 爬取降级链路 — MonitorResult 新增字段

**Files:**
- Modify: `backend/models/result.py`

- [ ] **Step 1: 添加 `crawl_method` 字段**

修改 `backend/models/result.py`：

```python
# intel-monitor/backend/models/result.py
from datetime import datetime, date
from sqlalchemy import Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class MonitorResult(Base):
    __tablename__ = "monitor_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    monitor_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawl_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # opencli/cdp/playwright
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    hot_comments = relationship("HotComment", backref="monitor_result", lazy="selectin")
```

- [ ] **Step 2: 生成数据库迁移**

```bash
cd /e/Gary/hebo/claude_projects/intel-monitor/backend
# If using alembic:
# alembic revision --autogenerate -m "add crawl_method to monitor_results"
# alembic upgrade head

# If using direct table creation (SQLite), the app will auto-create on next start
```

由于项目使用 SQLite 且 `Base.metadata.create_all` 模式，新字段会在重启后自动添加。如果是已有数据库，需要手动执行：

```sql
ALTER TABLE monitor_results ADD COLUMN crawl_method VARCHAR(20);
```

---

## Task 5: 爬取降级链路 — 实现 `crawl_with_fallback()`

**Files:**
- Modify: `backend/services/monitor.py`

- [ ] **Step 1: 实现 `crawl_with_fallback()` 函数**

在 `backend/services/monitor.py` 中新增降级链路函数，并重构 `_monitor_social_target()` 使用它：

```python
# intel-monitor/backend/services/monitor.py
import asyncio
import json
import sys
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from models.result import MonitorResult
from models.comment import HotComment
from crawlers import CRAWLER_MAP, WebsiteCrawler
from crawlers.opencli_crawler import crawl_with_opencli, _check_opencli
from crawlers.cdp_crawler import crawl_x_with_cdp, _check_cdp_proxy
from services.summarizer import summarizer

logger = logging.getLogger(__name__)

OPENCLI_PLATFORMS = ("x", "xiaohongshu", "reddit", "bilibili")

# CDP crawler mapping per platform
CDP_CRAWLERS = {
    "x": crawl_x_with_cdp,
}


async def _run_crawler_in_thread(coro):
    """Run a crawler coroutine in a thread with ProactorEventLoop on Windows."""
    if sys.platform == "win32":
        import concurrent.futures
        def run_in_proactor():
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await asyncio.get_event_loop().run_in_executor(pool, run_in_proactor)
    else:
        return await coro


async def crawl_with_fallback(
    platform: str,
    account_name: str,
    account_url: str,
    post_limit: int = 10,
    post_time_range_days: int = 0,
) -> tuple:
    """Try crawlers in order: OpenCLI → CDP → Playwright.
    Returns (CrawlResult, method_name, error_log).
    """
    error_log = []

    # 1. Try OpenCLI
    if platform in OPENCLI_PLATFORMS and _check_opencli():
        try:
            result = await crawl_with_opencli(platform, account_name, account_url)
            if result.success:
                return result, "opencli", error_log
            error_log.append(f"OpenCLI: {result.error_message}")
            logger.warning(f"OpenCLI failed for {account_name}: {result.error_message}")
        except Exception as e:
            error_log.append(f"OpenCLI: {str(e)}")
            logger.warning(f"OpenCLI exception for {account_name}: {e}")

    # 2. Try CDP
    cdp_func = CDP_CRAWLERS.get(platform)
    if cdp_func:
        try:
            if await _check_cdp_proxy():
                result = await cdp_func(account_url)
                if result.success:
                    return result, "cdp", error_log
                error_log.append(f"CDP: {result.error_message}")
                logger.warning(f"CDP failed for {account_name}: {result.error_message}")
            else:
                error_log.append("CDP: Proxy 未运行")
        except Exception as e:
            error_log.append(f"CDP: {str(e)}")
            logger.warning(f"CDP exception for {account_name}: {e}")

    # 3. Try Playwright (fallback)
    crawler_cls = CRAWLER_MAP.get(platform)
    if crawler_cls:
        try:
            crawler = crawler_cls()
            result = await _run_crawler_in_thread(crawler.crawl(account_url))
            if result.success:
                return result, "playwright", error_log
            error_log.append(f"Playwright: {result.error_message}")
            return result, "playwright", error_log
        except Exception as e:
            error_log.append(f"Playwright: {str(e)}")
            return None, "playwright", error_log

    return None, "none", error_log


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
    # Find or reuse pending result
    existing = await db.execute(
        select(MonitorResult)
        .where(
            MonitorResult.target_id == target.id,
            MonitorResult.target_type == "social_media",
            MonitorResult.status == "pending",
        )
        .order_by(MonitorResult.created_at.desc())
        .limit(1)
    )
    monitor_result = existing.scalar_one_or_none()

    if not monitor_result:
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
        crawl_result, method, error_log = await crawl_with_fallback(
            platform=target.platform,
            account_name=target.account_name,
            account_url=target.account_url,
            post_limit=getattr(target, 'post_limit', 10),
            post_time_range_days=getattr(target, 'post_time_range_days', 0),
        )

        monitor_result.crawl_method = method

        if not crawl_result or not crawl_result.success:
            monitor_result.status = "failed"
            monitor_result.error_message = " | ".join(error_log) if error_log else "所有爬取方式均失败"
            await db.commit()
            return

        # Get hot comments (only for Playwright method)
        all_comments = []
        if method == "playwright":
            crawler_cls = CRAWLER_MAP.get(target.platform)
            if crawler_cls:
                crawler = crawler_cls()
                for post in crawl_result.posts:
                    if post.url:
                        try:
                            comments = await _run_crawler_in_thread(crawler.get_hot_comments(post.url))
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
        crawl_result = await _run_crawler_in_thread(crawler.crawl(target.url, target.css_selector))

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
        monitor_result.crawl_method = "playwright"
        await db.commit()

    except Exception as e:
        monitor_result.status = "failed"
        monitor_result.error_message = str(e)
        await db.commit()


async def monitor_all_active():
    """Run monitoring for all active targets (called by scheduler)."""
    async with async_session() as db:
        result = await db.execute(select(Target).where(Target.is_active == True))
        targets = result.scalars().all()
        for target in targets:
            try:
                await execute_monitor(target.id, "social_media")
            except Exception:
                pass

        result = await db.execute(select(WebsiteTarget).where(WebsiteTarget.is_active == True))
        websites = result.scalars().all()
        for website in websites:
            try:
                await execute_monitor(website.id, "website")
            except Exception:
                pass
```

- [ ] **Step 2: 验证降级链路**

1. 确保 OpenCLI 未运行，点击执行一个 X 账号
2. 确认 MonitorResult 的 `crawl_method` 为 "cdp" 或 "playwright"
3. 确认 `error_message` 中记录了 OpenCLI 的失败原因
4. 确认最终状态为 success（如果 CDP 或 Playwright 成功）

---

## Task 6: 贴文参数 — 模型和过滤

**Files:**
- Modify: `backend/models/target.py`
- Modify: `backend/schemas/target.py`
- Modify: `backend/crawlers/base.py`
- Modify: `backend/crawlers/opencli_crawler.py`

- [ ] **Step 1: Target 模型新增字段**

修改 `backend/models/target.py`：

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
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_url: Mapped[str] = mapped_column(String(500), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    monitor_interval_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    monitor_hour: Mapped[int] = mapped_column(Integer, default=9)
    monitor_minute: Mapped[int] = mapped_column(Integer, default=0)
    cron_schedule: Mapped[str | None] = mapped_column(String(500), nullable=True)  # semicolon-separated cron expressions
    post_limit: Mapped[int] = mapped_column(Integer, default=10)
    post_time_range_days: Mapped[int] = mapped_column(Integer, default=0)  # 0 = no limit
    opencli_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verify_status: Mapped[str] = mapped_column(String(20), default="pending")
    last_verify_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: Schema 更新**

修改 `backend/schemas/target.py`：

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
    cron_schedule: Optional[str] = Field(None, max_length=500)
    post_limit: int = Field(default=10, ge=1, le=100)
    post_time_range_days: int = Field(default=0, ge=0, le=365)
    is_active: bool = True


class TargetUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=100)
    account_url: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    monitor_interval_minutes: Optional[int] = Field(None, ge=60)
    monitor_hour: Optional[int] = Field(None, ge=0, le=23)
    monitor_minute: Optional[int] = Field(None, ge=0, le=59)
    cron_schedule: Optional[str] = Field(None, max_length=500)
    post_limit: Optional[int] = Field(None, ge=1, le=100)
    post_time_range_days: Optional[int] = Field(None, ge=0, le=365)
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
    cron_schedule: Optional[str]
    post_limit: int
    post_time_range_days: int
    opencli_ready: bool
    last_verify_status: str
    last_verify_method: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: 在 base.py 中添加过滤函数**

在 `backend/crawlers/base.py` 末尾添加：

```python
from datetime import datetime, timedelta


def filter_posts(posts: list[PostData], post_limit: int = 10, time_range_days: int = 0) -> list[PostData]:
    """Filter posts by time range and limit count."""
    filtered = posts

    if time_range_days > 0:
        cutoff = datetime.utcnow() - timedelta(days=time_range_days)
        filtered = [
            p for p in filtered
            if p.published_at is None or p.published_at >= cutoff
        ]

    return filtered[:post_limit]
```

- [ ] **Step 4: OpenCLI 适配 post_limit**

修改 `backend/crawlers/opencli_crawler.py` 中 `_run_opencli` 函数的 `--limit` 参数，改为从调用方传入：

```python
# 修改 _run_opencli 签名，添加 limit 参数
async def _run_opencli(platform: str, username: str, limit: int = 10):
    # ...existing code...
    args.extend(["--limit", str(limit), "--format", "json"])
    # ...rest unchanged...
```

同时修改 `crawl_with_opencli` 函数签名：

```python
async def crawl_with_opencli(platform: str, account_name: str, account_url: str, limit: int = 10) -> CrawlResult:
    crawler = OpenCLICrawler(platform=platform)
    username = _extract_username(platform, account_url, account_name)

    if not _check_opencli():
        return CrawlResult(
            success=False,
            error_message="OpenCLI 未安装，请运行: npm install -g @jackwener/opencli"
        )

    try:
        data = await _run_opencli(platform, username, limit=limit)
        posts = _parse_posts(platform, data)

        if not posts:
            return CrawlResult(success=False, error_message="未提取到内容")

        return CrawlResult(posts=posts, success=True)

    except OpenCLIError as e:
        return CrawlResult(success=False, error_message=str(e))
    except Exception as e:
        return CrawlResult(success=False, error_message=str(e) or type(e).__name__)
```

- [ ] **Step 5: 在 monitor.py 的 crawl_with_fallback 中应用过滤**

在 `crawl_with_fallback` 函数中，对成功的结果应用过滤：

```python
from crawlers.base import filter_posts

# 在每个 crawler 成功后添加：
if result.success:
    result.posts = filter_posts(result.posts, post_limit, post_time_range_days)
    return result, method_name, error_log
```

- [ ] **Step 6: 数据库迁移**

```sql
ALTER TABLE targets ADD COLUMN cron_schedule VARCHAR(500);
ALTER TABLE targets ADD COLUMN post_limit INTEGER DEFAULT 10;
ALTER TABLE targets ADD COLUMN post_time_range_days INTEGER DEFAULT 0;
ALTER TABLE targets ADD COLUMN opencli_ready BOOLEAN DEFAULT 0;
ALTER TABLE targets ADD COLUMN last_verify_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE targets ADD COLUMN last_verify_method VARCHAR(20);
```

---

## Task 7: 前端表单 — 贴文参数 + Cron 模式

**Files:**
- Modify: `frontend/src/pages/SocialAccountsPage.tsx`

- [ ] **Step 1: 更新表单，添加贴文参数和 Cron 模式**

在 `SocialAccountsPage.tsx` 的 Modal 表单中，在 `is_active` 之前添加贴文参数字段和 cron 模式切换。

首先添加状态变量：

```tsx
const [scheduleMode, setScheduleMode] = useState<'simple' | 'cron'>('simple')
const [cronExpressions, setCronExpressions] = useState<string[]>([''])
```

在编辑时根据 target 数据设置模式：

```tsx
// 在 setEditingTarget 的 onClick 中添加
onClick={() => {
  setEditingTarget(record)
  form.setFieldsValue(record)
  if (record.cron_schedule) {
    setScheduleMode('cron')
    setCronExpressions(record.cron_schedule.split(';').filter(Boolean))
  } else {
    setScheduleMode('simple')
    setCronExpressions([''])
  }
  setModalOpen(true)
}}
```

在表单中，替换现有的监测时间字段（`monitor_hour` / `monitor_minute` 那个 `div`），并在 `is_active` 前添加贴文参数：

```tsx
{/* 调度模式 */}
<Form.Item label="调度模式">
  <Select
    value={scheduleMode}
    onChange={v => {
      setScheduleMode(v)
      if (v === 'cron' && cronExpressions.length === 0) setCronExpressions([''])
    }}
    options={[
      { value: 'simple', label: '每天定时' },
      { value: 'cron', label: '高级 Cron 表达式' },
    ]}
    style={{ width: 200 }}
  />
</Form.Item>

{scheduleMode === 'simple' ? (
  <div style={{ display: 'flex', gap: 16 }}>
    <Form.Item name="monitor_hour" label="监测小时" initialValue={9} style={{ flex: 1 }}>
      <InputNumber min={0} max={23} style={{ width: '100%' }} />
    </Form.Item>
    <Form.Item name="monitor_minute" label="监测分钟" initialValue={0} style={{ flex: 1 }}>
      <InputNumber min={0} max={59} style={{ width: '100%' }} />
    </Form.Item>
  </div>
) : (
  <Form.Item label="Cron 表达式">
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {cronExpressions.map((expr, idx) => (
        <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            value={expr}
            onChange={e => {
              const updated = [...cronExpressions]
              updated[idx] = e.target.value
              setCronExpressions(updated)
            }}
            placeholder="分 时 日 月 周 (如: 0 9 * * *)"
            style={{ flex: 1, fontFamily: 'var(--font-mono)' }}
          />
          {cronExpressions.length > 1 && (
            <Button
              danger
              size="small"
              onClick={() => setCronExpressions(cronExpressions.filter((_, i) => i !== idx))}
            >
              删除
            </Button>
          )}
        </div>
      ))}
      <Button
        type="dashed"
        size="small"
        onClick={() => setCronExpressions([...cronExpressions, ''])}
        style={{ width: 120 }}
      >
        + 添加定时
      </Button>
    </div>
  </Form.Item>
)}

{/* 贴文参数 */}
<div style={{ display: 'flex', gap: 16 }}>
  <Form.Item name="post_limit" label="抓取数量" initialValue={10} style={{ flex: 1 }}>
    <InputNumber min={1} max={100} style={{ width: '100%' }} addonAfter="条" />
  </Form.Item>
  <Form.Item name="post_time_range_days" label="时间范围" initialValue={0} style={{ flex: 1 }}>
    <InputNumber min={0} max={365} style={{ width: '100%' }} addonAfter="天" />
  </Form.Item>
</div>
<Text style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: -8, marginBottom: 16, display: 'block' }}>
  时间范围填 0 表示不限制
</Text>

<Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
  <Switch />
</Form.Item>
```

- [ ] **Step 2: 修改提交逻辑，组装 cron_schedule**

修改 `handleSubmit` 函数：

```tsx
const handleSubmit = async () => {
  const values = await form.validateFields()

  // Assemble cron_schedule from mode
  if (scheduleMode === 'cron') {
    const valid = cronExpressions.filter(e => e.trim())
    if (valid.length === 0) {
      message.warning('请至少添加一个 Cron 表达式')
      return
    }
    values.cron_schedule = valid.join(';')
    values.monitor_hour = 9  // default, ignored when cron_schedule is set
    values.monitor_minute = 0
  } else {
    values.cron_schedule = null
  }

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
    setCronExpressions([''])
    setScheduleMode('simple')
    fetchTargets()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '操作失败')
  }
}
```

- [ ] **Step 3: 更新监测时间列显示**

修改 `columns` 中的 `schedule` 列，支持显示 cron 表达式：

```tsx
{
  title: '监测时间',
  key: 'schedule',
  width: 180,
  render: (_: any, r: any) => {
    if (r.cron_schedule) {
      const exprs = r.cron_schedule.split(';').filter(Boolean)
      return (
        <div>
          {exprs.map((e: string, i: number) => (
            <Tag key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, marginBottom: 2 }}>{e}</Tag>
          ))}
        </div>
      )
    }
    return (
      <Text style={{ color: 'var(--accent)', fontFamily: "var(--font-mono)", fontSize: 14 }}>
        {String(r.monitor_hour).padStart(2, '0')}:{String(r.monitor_minute).padStart(2, '0')}
      </Text>
    )
  },
},
```

- [ ] **Step 4: 验证**

1. 添加账号时选择"高级 Cron 表达式"模式，输入 `0 9 * * *`，确认保存成功
2. 添加多个表达式 `0 9 * * *;0 14 * * *`，确认用分号存储
3. 设置抓取数量为 20，时间范围为 7 天，确认保存
4. 编辑已有账号，确认 cron 模式正确回显

---

## Task 8: 调度增强 — 后端多 Cron 支持

**Files:**
- Modify: `backend/services/scheduler.py`

- [ ] **Step 1: 更新 `refresh_jobs()` 支持多 cron 表达式**

```python
# intel-monitor/backend/services/scheduler.py
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import async_session
from models.target import Target
from models.website import WebsiteTarget
from services.monitor import execute_monitor
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

BJT = timezone(timedelta(hours=8))

scheduler = AsyncIOScheduler()


def setup_scheduler():
    """Initialize the scheduler."""
    if not scheduler.running:
        scheduler.start()


def _parse_cron_trigger(expr: str) -> CronTrigger | None:
    """Parse a 5-field cron expression into a CronTrigger."""
    parts = expr.strip().split()
    if len(parts) != 5:
        return None
    try:
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    except Exception:
        return None


async def refresh_jobs():
    """Reload all monitor jobs from database."""
    scheduler.remove_all_jobs()

    async with async_session() as db:
        # Social media targets
        result = await db.execute(select(Target).where(Target.is_active == True))
        targets = result.scalars().all()
        for t in targets:
            if t.cron_schedule:
                # Multiple cron expressions
                exprs = [e.strip() for e in t.cron_schedule.split(';') if e.strip()]
                for idx, expr in enumerate(exprs):
                    trigger = _parse_cron_trigger(expr)
                    if trigger:
                        scheduler.add_job(
                            execute_monitor,
                            trigger=trigger,
                            args=[t.id, "social_media"],
                            id=f"target_{t.id}_{idx}",
                            replace_existing=True,
                        )
                    else:
                        logger.warning(f"Invalid cron expression for target {t.id}: {expr}")
            else:
                # Simple daily schedule
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
            if w.cron_schedule:
                exprs = [e.strip() for e in w.cron_schedule.split(';') if e.strip()]
                for idx, expr in enumerate(exprs):
                    trigger = _parse_cron_trigger(expr)
                    if trigger:
                        scheduler.add_job(
                            execute_monitor,
                            trigger=trigger,
                            args=[w.id, "website"],
                            id=f"website_{w.id}_{idx}",
                            replace_existing=True,
                        )
                    else:
                        logger.warning(f"Invalid cron expression for website {w.id}: {expr}")
            else:
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
        next_run = None
        if job.next_run_time:
            dt = job.next_run_time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            next_run = dt.astimezone(BJT).strftime("%Y-%m-%d %H:%M:%S")
        jobs.append({
            "id": job.id,
            "next_run": next_run,
            "trigger": str(job.trigger),
        })
    return jobs
```

- [ ] **Step 2: 验证**

1. 添加一个 cron 模式的 target（如 `0 9 * * *;0 14 * * *`）
2. 调用 `POST /api/schedule/refresh`
3. 调用 `GET /api/schedule/status`，确认出现 `target_N_0` 和 `target_N_1` 两个 job
4. 确认 next_run 时间正确

---

## Task 9: SettingsPage 调度任务分组

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: 按 target 分组显示调度任务**

修改 SettingsPage 中 List 的渲染逻辑，按 target ID 分组：

```tsx
// 在 getJobStatus 返回数据后，按 target 分组
const groupedJobs = jobs.reduce((acc: Record<string, any[]>, job: any) => {
  // Extract target ID from job.id like "target_5_0" or "website_3"
  const match = job.id.match(/^(target|website)_(\d+)/)
  const key = match ? `${match[1]}_${match[2]}` : job.id
  if (!acc[key]) acc[key] = []
  acc[key].push(job)
  return acc
}, {})

// Replace the List component with grouped rendering
<List
  dataSource={Object.entries(groupedJobs)}
  locale={{ emptyText: <Text style={{ color: 'var(--text-muted)' }}>暂无调度任务</Text> }}
  renderItem={([groupKey, groupJobs]: [string, any[]]) => (
    <List.Item style={{
      background: 'var(--surface-1)',
      marginBottom: 10,
      padding: '18px 22px',
      borderRadius: 12,
      border: '1px solid var(--border)',
    }}>
      <div style={{ width: '100%' }}>
        <Text style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: 14, marginBottom: 8, display: 'block' }}>
          {groupKey}
        </Text>
        {groupJobs.map((job: any, idx: number) => (
          <div key={idx} style={{ display: 'flex', gap: 32, marginBottom: idx < groupJobs.length - 1 ? 8 : 0 }}>
            <Text style={{ color: 'var(--accent)', fontFamily: "var(--font-mono)", fontSize: 13, minWidth: 100 }}>
              {job.trigger}
            </Text>
            <Text style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
              下次: <span style={{ color: 'var(--accent)' }}>{job.next_run || '未安排'}</span>
            </Text>
          </div>
        ))}
      </div>
    </List.Item>
  )}
/>
```

- [ ] **Step 2: 验证**

1. 有多个 cron 表达式的 target，在设置页应分组显示
2. 每个表达式显示对应的 trigger 和 next_run

---

## Task 10: 新增账号预热验证 — 后端

**Files:**
- Modify: `backend/routers/targets.py`

- [ ] **Step 1: 创建 target 后触发异步预热验证**

修改 `backend/routers/targets.py` 的 `create_target` 函数：

```python
# intel-monitor/backend/routers/targets.py
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, async_session
from auth import get_current_user
from models.user import User
from models.target import Target
from schemas.target import TargetCreate, TargetUpdate, TargetResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/targets", tags=["targets"])


async def _warm_and_verify(target_id: int):
    """Pre-warm OpenCLI session and verify the target with a test crawl."""
    from services.monitor import crawl_with_fallback
    from crawlers.opencli_crawler import _check_opencli, crawl_with_opencli, _extract_username, PLATFORM_CMD
    import shutil

    async with async_session() as db:
        result = await db.execute(select(Target).where(Target.id == target_id))
        target = result.scalar_one_or_none()
        if not target:
            return

        # Step 1: OpenCLI pre-warm
        opencli_ready = False
        if target.platform in PLATFORM_CMD and _check_opencli():
            try:
                username = _extract_username(target.platform, target.account_url, target.account_name)
                # A lightweight call to warm up the session
                await crawl_with_opencli(target.platform, target.account_name, target.account_url, limit=3)
                opencli_ready = True
            except Exception as e:
                logger.warning(f"OpenCLI pre-warm failed for target {target_id}: {e}")

        target.opencli_ready = opencli_ready

        # Step 2: Verify with fallback crawl
        try:
            crawl_result, method, error_log = await crawl_with_fallback(
                platform=target.platform,
                account_name=target.account_name,
                account_url=target.account_url,
                post_limit=3,
            )

            if crawl_result and crawl_result.success:
                target.last_verify_status = "success"
                target.last_verify_method = method
            else:
                target.last_verify_status = "failed"
                target.last_verify_method = method
        except Exception as e:
            target.last_verify_status = "failed"
            logger.warning(f"Verification failed for target {target_id}: {e}")

        await db.commit()


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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = Target(user_id=user.id, **req.model_dump())
    db.add(target)
    await db.commit()
    await db.refresh(target)

    # Trigger async pre-warm and verification
    background_tasks.add_task(_warm_and_verify, target.id)

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

- [ ] **Step 2: 验证**

1. 添加一个新 X 账号
2. 确认 target 列表中该账号显示 `last_verify_status`
3. 等待几秒后刷新，确认状态变为 "success" 或 "failed"
4. 确认 `opencli_ready` 字段正确更新

---

## Task 11: 新增账号预热验证 — 前端

**Files:**
- Modify: `frontend/src/pages/SocialAccountsPage.tsx`

- [ ] **Step 1: 在表格中显示验证状态**

在 `SocialAccountsPage.tsx` 的 `columns` 数组中，在"状态"列后面添加"验证状态"列：

```tsx
{
  title: '验证',
  key: 'verify',
  width: 120,
  render: (_: any, r: any) => {
    const statusMap: Record<string, { color: string; label: string }> = {
      pending: { color: 'processing', label: '验证中...' },
      success: { color: 'success', label: '可用' },
      failed: { color: 'error', label: '不可用' },
    }
    const s = statusMap[r.last_verify_status] || statusMap.pending
    return (
      <div>
        <Tag color={s.color}>{s.label}</Tag>
        {r.last_verify_method && (
          <Text style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>
            via {r.last_verify_method}
          </Text>
        )}
      </div>
    )
  },
},
```

- [ ] **Step 2: 添加自动刷新逻辑**

当有 pending 验证状态的 target 时，自动轮询刷新：

```tsx
// 在 fetchTargets 后添加
useEffect(() => {
  const hasPendingVerify = targets.some(t => t.last_verify_status === 'pending')
  if (!hasPendingVerify) return

  const timer = setInterval(() => {
    fetchTargets()
  }, 3000)

  return () => clearInterval(timer)
}, [targets])
```

- [ ] **Step 3: 验证**

1. 添加新账号后，确认表格中出现"验证中..."标签
2. 等待几秒后自动刷新，标签变为"可用"或"不可用"
3. 确认 via 方法显示正确（opencli/cdp/playwright）

---

## Commit Strategy

每个 Task 完成后独立提交：

```bash
git add -A && git commit -m "feat: <task description>"
```

建议提交顺序：
1. Task 1 + 2: "feat: fix monitor status display with async execution and polling"
2. Task 3: "feat: improve login error feedback with Chinese messages"
3. Task 4 + 5: "feat: add crawl fallback chain (OpenCLI → CDP → Playwright)"
4. Task 6: "feat: add post_limit and post_time_range_days to target model"
5. Task 7: "feat: add cron schedule mode and post params to frontend form"
6. Task 8: "feat: support multiple cron expressions in scheduler"
7. Task 9: "feat: group scheduler jobs by target in settings page"
8. Task 10 + 11: "feat: add account pre-warm and verification on creation"
