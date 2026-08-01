# intel-monitor/backend/crawlers/telegram/__init__.py
"""
Telegram @kuai search crawler.

Public entry point: ``search_kuai(keyword, limit) -> CrawlResult``
"""
import asyncio
import logging
import re

from crawlers.base import CrawlResult, PostData
from crawlers.telegram.bot import TelegramBot, TelegramLoginRequired
from crawlers.telegram.parser import is_ad_result, parse_result_item_link

logger = logging.getLogger(__name__)

# Content types worth fetching full body for.
# 🎬 (video) results typically have little/no text — skip deep fetch.
FETCHABLE_ICON_TYPES = {"image", "document", "unknown"}

# Keywords that must match result title (at least one).
# Split from the user's search keyword (space-separated).


def _title_matches_keyword(title: str, keyword: str) -> bool:
    """Return True if at least one keyword token appears in the title."""
    if not title:
        return False
    tokens = [t.strip() for t in keyword.split() if t.strip() and len(t.strip()) >= 1]
    if not tokens:
        return True  # empty keyword → pass everything
    title_lower = title.lower()
    for token in tokens:
        # Skip single-char tokens (e.g. "的", "了") unless they are Latin letters
        if len(token) == 1 and not token.isascii():
            continue
        if token.lower() in title_lower:
            return True
    return False


async def search_kuai(keyword: str, limit: int = 20) -> CrawlResult:
    """Search @kuai Bot for *keyword*, fetch full body for each result.

    Args:
        keyword: Search query sent to the @kuai Bot.
        limit: Max number of results to deep-fetch.

    Returns:
        CrawlResult with posts populated; success=False on catastrophic failure.
    """
    bot = TelegramBot()
    error_log: list[str] = []
    total_found = 0
    skipped = 0
    successfully_fetched = 0
    posts: list[PostData] = []

    try:
        await bot.start()
    except TelegramLoginRequired as e:
        return CrawlResult(success=False, error_message=str(e))
    except Exception as e:
        logger.exception("Failed to start TelegramBot")
        return CrawlResult(success=False, error_message=f"Telegram browser 启动失败: {e}")

    try:
        # 1. Navigate to @kuai
        await bot._navigate_to_kuai()

        # 2. Send keyword
        await bot.send_message(keyword)

        # 3. Wait for Bot reply
        result_items = await bot.wait_for_bot_reply()
        total_found = len(result_items)
        logger.info("@kuai returned %d result items for '%s'", total_found, keyword)

        if not result_items:
            return CrawlResult(
                success=True,
                posts=[],
                error_message="",
            )

        # 4. Filter: skip ads, skip video-only, skip non-matching keywords,
        #    skip items we can't get a URL for, and respect limit
        to_fetch = []
        for item in result_items:
            title = item.get("title", "")
            url = item.get("url", "")
            icon_type = item.get("icon_type", "unknown")

            # Skip ads
            if item.get("is_ad") or is_ad_result(title):
                skipped += 1
                logger.debug("Skipping ad: %s", title[:60])
                continue

            # Skip non-fetchable content types
            if icon_type not in FETCHABLE_ICON_TYPES:
                # For video results, still include as title-only entries
                if icon_type == "video":
                    if _title_matches_keyword(title, keyword):
                        posts.append(PostData(
                            url=url,
                            title=title[:200],
                            content=title[:200],
                        ))
                        successfully_fetched += 1
                else:
                    skipped += 1
                continue

            # Skip non-matching keywords
            if not _title_matches_keyword(title, keyword):
                skipped += 1
                logger.debug("Skipping non-matching: %s", title[:60])
                continue

            if not url:
                skipped += 1
                continue

            to_fetch.append(item)

        to_fetch = to_fetch[:limit]

        # 5. Serial deep fetch: navigate → extract → return → next
        for item in to_fetch:
            url = item.get("url", "")
            title = item.get("title", "")
            try:
                post = await bot.click_result_and_extract(url)
                if post and post.content:
                    # Preserve the original @kuai result title if channel extraction
                    # produced a better one
                    successfully_fetched += 1
                    posts.append(post)
                elif post:
                    # Extraction succeeded but no meaningful content —
                    # still use the result title
                    post.title = title[:200]
                    successfully_fetched += 1
                    posts.append(post)
                else:
                    # Extraction failed entirely — keep as title-only
                    error_log.append(f"{url}（内容提取失败）")
                    posts.append(PostData(
                        url=url,
                        title=title[:200],
                        content=title[:200],
                    ))
            except Exception as e:
                error_log.append(f"{url}（{e}）")
                logger.warning("Deep fetch error for %s: %s", url, e)

            # Rate-limit between fetches
            await asyncio.sleep(1.5)

    except Exception as e:
        logger.exception("Error during @kuai search")
        error_log.insert(0, f"搜索异常: {e}")
    finally:
        try:
            await bot.close()
        except Exception:
            pass

    logger.info(
        "Telegram @kuai search done: found=%d, skipped=%d, fetched=%d, total_posts=%d",
        total_found, skipped, successfully_fetched, len(posts),
    )

    return CrawlResult(
        success=len(posts) > 0,
        posts=posts,
        error_message=(
            "; ".join(error_log)
            if error_log
            else ("" if len(posts) > 0 else "@kuai 未返回任何匹配结果")
        ),
    )


# Convenience alias for router/dispatch compatibility
search_by_keyword = search_kuai
