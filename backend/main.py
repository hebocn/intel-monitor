# intel-monitor/backend/main.py
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

# 配置应用日志 - 与 uvicorn 格式统一
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:\t%(name)s - %(message)s",
)
# 降低第三方库日志噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db, engine
from routers import auth, targets, websites, results, dashboard, schedule, settings, tools, hot_topics, sentiment, intelligence
from services.scheduler import setup_scheduler, refresh_jobs


async def _ensure_schema():
    """Auto-add missing columns to existing tables (no Alembic)."""
    import re
    from sqlalchemy import text

    migrations = [
        # migration_id, check_sql, apply_sql
        (
            "sentiment_posts_deep_analysis_status",
            "SELECT deep_analysis_status FROM sentiment_posts LIMIT 0",
            "ALTER TABLE sentiment_posts ADD COLUMN deep_analysis_status VARCHAR(20) DEFAULT NULL",
        ),
    ]

    async with engine.begin() as conn:
        for migration_id, check_sql, apply_sql in migrations:
            try:
                await conn.execute(text(check_sql))
            except Exception:
                logger = logging.getLogger("migration")
                logger.info(f"Applying migration: {migration_id}")
                try:
                    await conn.execute(text(apply_sql))
                    logger.info(f"Migration {migration_id} applied successfully")
                except Exception as e:
                    logger.warning(f"Migration {migration_id} failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _ensure_schema()
    setup_scheduler()
    await refresh_jobs()
    yield


app = FastAPI(title="Intel Monitor", lifespan=lifespan)

# Include routers
app.include_router(auth.router)
app.include_router(targets.router)
app.include_router(websites.router)
app.include_router(results.router)
app.include_router(dashboard.router)
app.include_router(schedule.router)
app.include_router(settings.router)
app.include_router(tools.router)
app.include_router(hot_topics.router)
app.include_router(sentiment.router)
app.include_router(intelligence.router)

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
