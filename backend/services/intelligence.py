# intel-monitor/backend/services/intelligence.py
"""战略情报报告生成主编排 — 搜索 → 筛选 → 深度抓取 → AI 流水线。"""

import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select
from database import async_session
from models.intelligence_report import IntelligenceReport
from services.firecrawl_service import firecrawl, FirecrawlError
from services.report_writer import split_query, filter_sources, run_report_writer

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

WEB_SEARCH_PLATFORMS = {
    "firecrawl": "Firecrawl (Google/Bing web)",
    "tavily": "Tavily (AI-powered web search)",
}

CRAWLER_PLATFORMS = {
    "weibo": "微博",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "toutiao": "今日头条",
    "108community": "108天台社区",
    "x": "X (Twitter)",
}


async def _update_progress(report_id: int, status: str, phase: str, message: str):
    """Update report status and progress detail."""
    message_clean = message.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
    async with async_session() as db:
        report = await db.get(IntelligenceReport, report_id)
        if report:
            report.status = status
            report.progress_detail = json.dumps(
                {"phase": phase, "message": message_clean}, ensure_ascii=False
            )
            await db.commit()


async def _update_error(report_id: int, error_log: dict):
    """Set report to failed and record error log."""
    async with async_session() as db:
        report = await db.get(IntelligenceReport, report_id)
        if report:
            report.status = "failed"
            error_str = json.dumps(error_log, ensure_ascii=False)
            clean_error = error_str.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
            report.error_log = clean_error
            report.completed_at = datetime.utcnow()
            await db.commit()


async def _update_completed(report_id: int, markdown: str, sources: list[dict]):
    """Set report to completed with final content."""
    async with async_session() as db:
        report = await db.get(IntelligenceReport, report_id)
        if report:
            # Sanitize: remove surrogate characters that break JSON encoding
            clean_markdown = markdown.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
            report.status = "completed"
            report.report_markdown = clean_markdown
            report.sources_json = json.dumps(sources, ensure_ascii=False)
            report.progress_detail = json.dumps(
                {"phase": "completed", "message": f"报告生成完成，共引用 {len(sources)} 条来源"},
                ensure_ascii=False,
            )
            report.completed_at = datetime.utcnow()
            await db.commit()


# ── Dual-track search ──────────────────────────────────────────────────────

async def _search_web(query: str, engines: list[str], max_results: int) -> list[dict]:
    """Search via web engines (Firecrawl + Tavily). 也用于 X 关键词搜索的 fallback。"""
    results = []
    if "firecrawl" in engines:
        try:
            hits = await firecrawl.search(
                query=query,
                limit=min(max_results, 10),  # Per query, don't overwhelm
            )
            for h in hits:
                h["source_engine"] = "firecrawl"
                h["search_query"] = query
                h["source_type"] = "web"
            results.extend(hits)
        except FirecrawlError as e:
            logger.warning(f"Firecrawl search failed for '{query[:60]}': {e}")
        except Exception as e:
            logger.warning(f"Firecrawl unexpected error for '{query[:60]}': {e}")
    if "tavily" in engines:
        from services.tavily_service import tavily, TavilyError
        try:
            hits = await tavily.search(
                query=query,
                max_results=min(max_results, 10),
                search_depth="advanced",
                include_raw_content=True,
            )
            for h in hits:
                h["source_engine"] = "tavily"
                h["search_query"] = query
                h["source_type"] = "web"
            results.extend(hits)
        except TavilyError as e:
            logger.warning(f"Tavily search failed for '{query[:60]}': {e}")
        except Exception as e:
            logger.warning(f"Tavily unexpected error for '{query[:60]}': {e}")
    return results


async def _search_platform_crawler(platform: str, keyword: str, limit: int) -> list[dict]:
    """Search a single platform using existing crawlers."""
    from crawlers.base import PostData, CrawlResult, _run_crawler_in_thread
    from crawlers.weibo_crawler import WeiboCrawler, search_weibo_via_autocli
    from crawlers.douyin_crawler import DouyinCrawler
    from crawlers.toutiao_crawler import ToutiaoCrawler
    from crawlers.tiantai108_crawler import Tiantai108Crawler
    from crawlers.opencli_crawler import search_x_via_opencli

    try:
        result = CrawlResult(posts=[], success=False, error_message="")

        if platform == "weibo":
            result = await search_weibo_via_autocli(keyword, limit=limit)
            if not result.success:
                logger.warning(f"Weibo autocli failed: {result.error_message}, trying Playwright...")
                crawler = WeiboCrawler()
                result = await _run_crawler_in_thread(
                    crawler.search_by_keyword(keyword, limit=limit)
                )
        elif platform == "douyin":
            crawler = DouyinCrawler()
            result = await crawler.search_by_keyword(keyword, limit=limit)
        elif platform == "xiaohongshu":
            from crawlers.opencli_crawler import crawl_with_opencli
            result = await crawl_with_opencli("xiaohongshu", keyword, "", limit)
        elif platform == "toutiao":
            crawler = ToutiaoCrawler()
            result = await crawler.search_by_keyword(keyword, limit=limit)
        elif platform == "108community":
            crawler = Tiantai108Crawler()
            result = await _run_crawler_in_thread(
                crawler.search_by_keyword(keyword, limit=limit)
            )
        elif platform == "x":
            # Try OpenCLI X search first (reuses Chrome login), fall back to Firecrawl domain-filtered
            result = await search_x_via_opencli(keyword, limit=limit)
            if not result.success:
                logger.warning(f"X OpenCLI search failed: {result.error_message}, will fall back to Firecrawl x.com filter")
        elif platform == "108community":
            crawler = Tiantai108Crawler()
            result = await _run_crawler_in_thread(
                crawler.search_by_keyword(keyword, limit=limit)
            )

        if result.success and result.posts:
            sources = []
            for post in result.posts:
                sources.append({
                    "title": post.title or post.content[:80] if post.content else "",
                    "description": (post.content or "")[:300],
                    "url": post.url or "",
                    "markdown": post.content or post.title or "",
                    "source_engine": platform,
                    "search_query": keyword,
                    "source_type": "social",
                    "author_name": post.author_name or "",
                    "published_at": post.published_at.isoformat() if post.published_at else "",
                    "likes": post.likes,
                    "comments": post.comments_count,
                    "shares": post.shares,
                    "views": post.views,
                    "images": post.images,
                })
            return sources
        else:
            logger.warning(f"Platform {platform} search returned no results: {result.error_message}")
            return []
    except Exception as e:
        logger.warning(f"Platform crawler error for {platform}: {e}")
        return []


async def _search_all(
    queries: list[dict],
    engines: list[str],
    crawler_platforms: list[str],
    max_results: int,
    report_id: int,
) -> tuple[list[dict], dict]:
    """Execute all searches concurrently and return merged results + error log."""
    all_results: list[dict] = []
    error_log: dict[str, str] = {}
    seen_urls: set[str] = set()

    async def search_one(query: str, dim: str):
        """Search one query across all engines + platforms."""
        tasks = []

        # Web engines
        for engine in engines:
            tasks.append(_search_web(query, [engine], max_results))

        # Platform crawlers
        for platform in crawler_platforms:
            tasks.append(_search_platform_crawler(platform, query, max_results))
            # For X platform, also add a Firecrawl x.com domain-filtered search as fallback
            if platform == "x" and "firecrawl" in engines:
                tasks.append(_search_web(query + " site:x.com", ["firecrawl"], max_results))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning(f"Search task error: {r}")
            elif isinstance(r, list):
                for item in r:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        item["dimension"] = dim
                        all_results.append(item)

    # Run queries concurrently
    query_tasks = [
        search_one(q["query"], q.get("dimension", ""))
        for q in queries
    ]
    await asyncio.gather(*query_tasks, return_exceptions=True)

    return all_results, error_log


async def _deep_scrape_sources(
    sources: list[dict],
    engines: list[str],
    report_id: int,
) -> list[dict]:
    """Deep scrape high-relevance sources with short content."""
    if "firecrawl" not in engines:
        return sources

    updated = []
    for i, s in enumerate(sources):
        relevance = s.get("relevance", "medium")
        markdown_len = len(s.get("markdown", "") or "")
        should_deep_scrape = (
            relevance == "high" and markdown_len < 500
        )

        if should_deep_scrape and s.get("url"):
            await _update_progress(
                report_id, "scraping", "scraping",
                f"深度抓取 {i+1}/{len(sources)}: {s.get('title','')[:50]}"
            )
            deep_result = await firecrawl.scrape(s["url"])
            if deep_result and deep_result.get("markdown"):
                s["markdown"] = deep_result["markdown"]
                s["deep_scraped"] = True
            else:
                s["deep_scraped"] = False
        else:
            s["deep_scraped"] = False
        updated.append(s)

    return updated


# ── Main orchestrator ──────────────────────────────────────────────────────

async def run_report_generation(
    report_id: int,
    topic: str,
    engines: list[str] | None = None,
    crawler_platforms: list[str] | None = None,
    max_search_results: int = 10,
    max_sources: int = 30,
    half_life_days: float = 30.0,
):
    """Main report generation pipeline. Runs as a background asyncio task."""
    if engines is None:
        engines = ["firecrawl"]
    if crawler_platforms is None:
        crawler_platforms = []

    error_log = {}
    sources = []

    try:
        # ── Phase 1: Split query ──
        await _update_progress(report_id, "searching", "splitting",
                               "AI 正在拆解搜索查询...")
        logger.info(f"Report {report_id}: splitting query...")
        queries = await split_query(topic)
        logger.info(f"Report {report_id}: split into {len(queries)} queries")
        if not queries:
            queries = [{"query": topic[:200], "dimension": "主搜索"}]

        # Save queries (sanitize for JSON safety)
        queries_json = json.dumps(queries, ensure_ascii=False)
        clean_queries = queries_json.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
        async with async_session() as db:
            report = await db.get(IntelligenceReport, report_id)
            if report:
                report.search_queries = clean_queries
                await db.commit()

        # ── Phase 2: Search ──
        await _update_progress(report_id, "searching", "searching",
                               f"正在 {len(engines)} 个搜索引擎 + {len(crawler_platforms)} 个平台搜索 {len(queries)} 条查询...")
        logger.info(f"Report {report_id}: searching {len(queries)} queries across {len(engines)} engines + {len(crawler_platforms)} crawlers")

        sources, search_errors = await _search_all(
            queries, engines, crawler_platforms, max_search_results, report_id
        )
        if search_errors:
            error_log["search"] = search_errors

        logger.info(f"Report {report_id}: got {len(sources)} raw results")

        if not sources:
            # No results at all — try a direct topic search as fallback
            logger.info(f"Report {report_id}: no results from split queries, trying direct topic search")
            sources, _ = await _search_all(
                [{"query": topic[:200], "dimension": "整体搜索"}],
                engines, crawler_platforms, max_search_results, report_id
            )
            logger.info(f"Report {report_id}: fallback got {len(sources)} results")

        # ── Phase 3: Filter & Deep Scrape ──
        await _update_progress(report_id, "analyzing", "filtering",
                               f"正在用 AI 筛选 {len(sources)} 条搜索结果...")
        filtered = await filter_sources(topic, sources)
        logger.info(f"Report {report_id}: filtered to {len(filtered)} relevant sources")

        # Limit sources for quality
        if len(filtered) > max_sources:
            # Sort by relevance (high first), then take top N
            relevance_order = {"high": 0, "medium": 1, "low": 2}
            filtered.sort(key=lambda s: relevance_order.get(s.get("relevance", "low"), 2))
            filtered = filtered[:max_sources]

        logger.info(f"Report {report_id}: using {len(filtered)} sources (max={max_sources})")

        await _update_progress(report_id, "scraping", "scraping",
                               f"正在深度抓取精选链接...")
        filtered = await _deep_scrape_sources(filtered, engines, report_id)

        # ── Phase 4: AI Pipeline ──
        await _update_progress(report_id, "writing", "writing",
                               f"AI 正在撰写报告（阶段 1/3：事实提取）...")
        logger.info(f"Report {report_id}: starting AI pipeline with {len(filtered)} sources")

        final_markdown = await run_report_writer(topic, filtered)

        # ── Phase 5: Complete ──
        # Clean sources for storage (remove large markdown for storage efficiency,
        # keep summaries)
        storage_sources = []
        for s in filtered:
            storage_sources.append({
                "url": s.get("url", ""),
                "title": s.get("title", ""),
                "description": s.get("description", ""),
                "source_engine": s.get("source_engine", ""),
                "source_type": s.get("source_type", ""),
                "search_query": s.get("search_query", ""),
                "dimension": s.get("dimension", ""),
                "relevance": s.get("relevance", "medium"),
                "relevance_reason": s.get("relevance_reason", ""),
                "markdown_snippet": (s.get("markdown") or "")[:500],
                "author_name": s.get("author_name", ""),
                "published_at": s.get("published_at", ""),
            })

        await _update_completed(report_id, final_markdown, storage_sources)
        logger.info(f"Report {report_id}: COMPLETED — {len(final_markdown)} chars, {len(storage_sources)} sources")

    except Exception as e:
        logger.exception(f"Report {report_id}: FATAL error in generation pipeline")
        error_log["fatal"] = str(e)
        # Don't call _update_error directly as there may be a transaction issue
        # from the exception. Instead, catch the specific error states.
        # But fallback: try to save what we have
        try:
            async with async_session() as db:
                report = await db.get(IntelligenceReport, report_id)
                if report:
                    # If we have partial markdown, save it
                    if report.report_markdown is None:
                        report.status = "failed"
                        report.error_log = json.dumps(error_log, ensure_ascii=False)
                        report.completed_at = datetime.utcnow()
                    await db.commit()
        except Exception:
            pass  # Last resort: just log

        # Try one more time with a fresh session
        try:
            await _update_error(report_id, error_log)
        except Exception:
            logger.exception(f"Report {report_id}: Could not even save error state")
