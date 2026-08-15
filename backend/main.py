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
from routers import auth, targets, websites, results, dashboard, schedule, settings, tools, hot_topics, sentiment, intelligence, account_match, weather, feishu
from services.scheduler import setup_scheduler, refresh_jobs
from services.feishu import start_feishu_client, stop_feishu_client


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
        (
            "sentiment_posts_quoted_tweet_json",
            "SELECT quoted_tweet_json FROM sentiment_posts LIMIT 0",
            "ALTER TABLE sentiment_posts ADD COLUMN quoted_tweet_json TEXT DEFAULT NULL",
        ),
        (
            "sentiment_posts_card_json",
            "SELECT card_json FROM sentiment_posts LIMIT 0",
            "ALTER TABLE sentiment_posts ADD COLUMN card_json TEXT DEFAULT NULL",
        ),
        (
            "sentiment_posts_sort_order",
            "SELECT sort_order FROM sentiment_posts LIMIT 0",
            "ALTER TABLE sentiment_posts ADD COLUMN sort_order INTEGER DEFAULT 0",
        ),
        (
            "account_match_tasks",
            "SELECT 1 FROM account_match_tasks LIMIT 0",
            """CREATE TABLE IF NOT EXISTS account_match_tasks (
                id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                target_name VARCHAR(100) NOT NULL, platforms VARCHAR(200) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                total_candidates INTEGER DEFAULT 0, total_groups INTEGER DEFAULT 0,
                error_log TEXT, match_mode VARCHAR(20) DEFAULT 'nickname',
                anchor_profile_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME, PRIMARY KEY (id),
                FOREIGN KEY(user_id) REFERENCES users (id)
            )""",
        ),
        (
            "account_match_tasks_match_mode",
            "SELECT match_mode FROM account_match_tasks LIMIT 0",
            "ALTER TABLE account_match_tasks ADD COLUMN match_mode VARCHAR(20) DEFAULT 'nickname'",
        ),
        (
            "account_match_tasks_anchor_profile",
            "SELECT anchor_profile_json FROM account_match_tasks LIMIT 0",
            "ALTER TABLE account_match_tasks ADD COLUMN anchor_profile_json TEXT DEFAULT NULL",
        ),
        (
            "account_match_candidates",
            "SELECT 1 FROM account_match_candidates LIMIT 0",
            """CREATE TABLE IF NOT EXISTS account_match_candidates (
                id INTEGER NOT NULL, task_id INTEGER NOT NULL,
                platform VARCHAR(20) NOT NULL, platform_uid VARCHAR(200) NOT NULL,
                nickname VARCHAR(100) NOT NULL, avatar_url VARCHAR(500),
                bio TEXT, followers_count INTEGER DEFAULT 0,
                profile_url VARCHAR(500), profile_json TEXT, posts_json TEXT,
                match_score FLOAT DEFAULT 0.0,
                score_detail_json TEXT,
                matched_with VARCHAR(200),
                PRIMARY KEY (id),
                FOREIGN KEY(task_id) REFERENCES account_match_tasks (id)
            )""",
        ),
        (
            "account_match_candidates_match_score",
            "SELECT match_score FROM account_match_candidates LIMIT 0",
            "ALTER TABLE account_match_candidates ADD COLUMN match_score FLOAT DEFAULT 0.0",
        ),
        (
            "account_match_candidates_score_detail",
            "SELECT score_detail_json FROM account_match_candidates LIMIT 0",
            "ALTER TABLE account_match_candidates ADD COLUMN score_detail_json TEXT DEFAULT NULL",
        ),
        (
            "account_match_candidates_matched_with",
            "SELECT matched_with FROM account_match_candidates LIMIT 0",
            "ALTER TABLE account_match_candidates ADD COLUMN matched_with VARCHAR(200) DEFAULT NULL",
        ),
        (
            "account_match_results",
            "SELECT 1 FROM account_match_results LIMIT 0",
            """CREATE TABLE IF NOT EXISTS account_match_results (
                id INTEGER NOT NULL, task_id INTEGER NOT NULL,
                group_label VARCHAR(100) NOT NULL, confidence_score FLOAT DEFAULT 0.0,
                account_ids_json TEXT NOT NULL, ai_analysis TEXT,
                score_detail TEXT,
                PRIMARY KEY (id),
                FOREIGN KEY(task_id) REFERENCES account_match_tasks (id)
            )""",
        ),
        (
            "account_match_results_score_detail",
            "SELECT score_detail FROM account_match_results LIMIT 0",
            "ALTER TABLE account_match_results ADD COLUMN score_detail TEXT DEFAULT NULL",
        ),
        (
            "monitor_results_comments_ai_status",
            "SELECT comments_ai_status FROM monitor_results LIMIT 0",
            "ALTER TABLE monitor_results ADD COLUMN comments_ai_status VARCHAR(20) DEFAULT 'idle'",
        ),
        (
            "hot_comments_rank_counts",
            "SELECT global_rank FROM hot_comments LIMIT 0",
            "ALTER TABLE hot_comments ADD COLUMN global_rank INTEGER DEFAULT 0",
        ),
        (
            "hot_comments_reply_count",
            "SELECT reply_count FROM hot_comments LIMIT 0",
            "ALTER TABLE hot_comments ADD COLUMN reply_count INTEGER DEFAULT 0",
        ),
        (
            "hot_comments_retweet_count",
            "SELECT retweet_count FROM hot_comments LIMIT 0",
            "ALTER TABLE hot_comments ADD COLUMN retweet_count INTEGER DEFAULT 0",
        ),
        (
            "users_feishu_open_id",
            "SELECT feishu_open_id FROM users LIMIT 0",
            "ALTER TABLE users ADD COLUMN feishu_open_id VARCHAR(64)",
        ),
        (
            "users_feishu_push_enabled",
            "SELECT feishu_push_enabled FROM users LIMIT 0",
            "ALTER TABLE users ADD COLUMN feishu_push_enabled BOOLEAN DEFAULT 1",
        ),
        (
            "targets_push_enabled",
            "SELECT push_enabled FROM targets LIMIT 0",
            "ALTER TABLE targets ADD COLUMN push_enabled BOOLEAN DEFAULT 1",
        ),
        (
            "website_targets_push_enabled",
            "SELECT push_enabled FROM website_targets LIMIT 0",
            "ALTER TABLE website_targets ADD COLUMN push_enabled BOOLEAN DEFAULT 1",
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
    start_feishu_client()
    yield
    stop_feishu_client()


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
app.include_router(account_match.router)
app.include_router(weather.router)
app.include_router(feishu.router)

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
    uvicorn.run(
        "main:app", host=settings.HOST, port=settings.PORT, reload=True,
        # 排除 tests/data/缓存目录，避免测试或数据变化触发 reload 丢失内存态（如飞书绑定码）
        reload_excludes=["tests*", "data*", "*.pyc", "__pycache__*"],
    )
