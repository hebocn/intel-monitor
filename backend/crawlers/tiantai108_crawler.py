# intel-monitor/backend/crawlers/tiantai108_crawler.py
"""
108sq.cn (天台社区) crawler — direct JSONP API approach.

The search page at /shuo/search?key=KEYWORD uses a JS widget (TCSayList) that
calls the JSONP API:

    GET /shuo/Talk/AjaxGetInfoList?siteID={siteID}&orderBy=0&pageIndex=1
        &nPageRecord={limit}&sKey={keyword}&nContainUserName=1

Response format:
    callback(total, [[infoId, content, timestamp, userId, username,
                      commentCount, upCount, ?, title, images, ?, ?,
                      platform, ?, ?, ?, ?], ...], serverTime, pageCount)

The old approach (Playwright + DOM selectors) was broken for three reasons:
1. Wrong search URL patterns — /search?keyword=... returns 500
   (correct: /shuo/search?key=...)
2. The results page is JS-rendered — bare HTML has empty TCSayList div
3. DOM selectors didn't match the actual TCSayList_li structure
"""
import json
import logging
import re
import httpx
from datetime import datetime
from urllib.parse import quote

from crawlers.base import CrawlResult, PostData, CommentData

logger = logging.getLogger(__name__)

# tiantai.108sq.cn → siteID 67; other sites have different IDs
SITE_ID = 67
BASE_URL = "https://tiantai.108sq.cn"
API_URL = f"{BASE_URL}/shuo/Talk/AjaxGetInfoList"
POST_URL_PREFIX = f"{BASE_URL}/shuo/"


async def search_108community(keyword: str, limit: int = 20) -> CrawlResult:
    """Search 108sq.cn via the JSONP API. Returns CrawlResult with PostData list."""

    try:
        params = {
            "siteID": SITE_ID,
            "orderBy": 0,
            "pageIndex": 1,
            "nPageRecord": max(limit, 20),
            "nContainUserName": 1,
            "sKey": keyword,
        }
        url = f"{API_URL}?siteID={SITE_ID}&orderBy=0&pageIndex=1&nPageRecord={max(limit, 20)}&sKey={quote(keyword)}&nContainUserName=1"

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.text

        posts = _parse_jsonp_response(body, limit)
        return CrawlResult(posts=posts, success=len(posts) > 0)

    except httpx.TimeoutException:
        return CrawlResult(success=False, error_message="Request timed out")
    except Exception as e:
        logger.exception(f"108community search error for '{keyword}'")
        return CrawlResult(success=False, error_message=str(e))


def _js_array_to_json(js_literal: str) -> str:
    """Convert a JavaScript array literal to valid JSON.

    Handles: single-quoted strings, barewords (false, null, true),
    trailing commas, and unquoted numeric keys.
    """
    result = []
    i = 0
    n = len(js_literal)

    def peek():
        return js_literal[i] if i < n else '\0'

    def consume():
        nonlocal i
        c = js_literal[i]
        i += 1
        return c

    while i < n:
        ch = peek()

        if ch in (' ', '\t', '\n', '\r'):
            consume()
            result.append(ch)
            continue

        if ch == "'":
            # Single-quoted string → double-quoted with internal escapes
            consume()
            result.append('"')
            while peek() != "'" and peek() != '\0':
                c = consume()
                if c == '\\':
                    result.append('\\')
                    if peek() != '\0':
                        result.append(consume())
                elif c == '"':
                    result.append('\\"')
                elif c == '\n':
                    result.append('\\n')
                else:
                    result.append(c)
            if peek() == "'":
                consume()
            result.append('"')
        else:
            # Pass through everything else (numbers, brackets, commas, colons,
            # double-quoted strings, bareword identifiers like false/null/true/undefined)
            result.append(consume())

    raw = ''.join(result)

    # Replace bareword JavaScript identifiers with JSON equivalents
    raw = re.sub(r'(?<![\.\w])undefined(?![\.\w])', 'null', raw)
    # JavaScript allows trailing commas in arrays; JSON forbids them
    raw = re.sub(r',\s*(\]|\})', r'\1', raw)

    return raw


def _parse_jsonp_response(text: str, limit: int) -> list[PostData]:
    """Parse the JSONP callback into PostData objects.

    Format: callback(total, [[id, content, ts, uid, username, comments, up, ...], ...], serverTime, pageCount)
    """
    # Strip the JSONP wrapper: "callback (...)"  →  [...]
    # Response may have leading whitespace/newlines before the callback
    text = text.strip()
    match = re.match(r'^\w+\s*\(', text)
    if not match:
        logger.warning(f"108community: unexpected JSONP format, first 200 chars: {text[:200]}")
        return []

    # Remove the callback name + opening paren, and the trailing ");"
    json_str = text[match.end():].rstrip(");").strip()

    # The body is: totalCount, [...items...], serverTimestamp, pageCount
    # This isn't valid JSON (comma-separated values). Use regex to extract the items array.
    # Match: number, [ ...nested arrays... ], number, number
    # Use greedy .+ to span all nested arrays, backtracking to the last "],"
    items_match = re.search(r'\d+\s*,\s*(\[.+\])\s*,', json_str)
    if not items_match:
        logger.warning(f"108community: couldn't extract items array, body={json_str[:300]}")
        return []

    items_raw = items_match.group(1)

    # The items array uses JavaScript literal syntax (single-quoted strings, barewords
    # like false/null). Convert to valid JSON before parsing.
    items_json = _js_array_to_json(items_raw)

    try:
        items = json.loads(items_json)
    except json.JSONDecodeError:
        logger.exception(f"108community: failed to decode items JSON, raw={items_raw[:500]}")
        return []

    if not isinstance(items, list):
        logger.warning(f"108community: items is not a list: {type(items)}")
        return []

    posts = []
    for item in items[:limit]:
        if not isinstance(item, list) or len(item) < 9:
            continue

        try:
            info_id = item[0] or 0
            content = (item[1] or "").strip()
            timestamp = item[2] or 0
            user_id = item[3] or 0
            username = (item[4] or "").strip()
            comment_count = item[5] or 0
            up_count = item[6] or 0
            title = (item[8] or "").strip()
            images_raw = item[9] or ""

            # Use title if present, otherwise extract from content
            display_title = title if title else _extract_title_from_content(content)

            url = f"{POST_URL_PREFIX}{info_id}" if info_id else ""

            # Parse publish time (Unix timestamp)
            published_at = datetime.utcfromtimestamp(timestamp) if timestamp else None

            # Parse images: "id,url,idx,WxH|id,url,idx,WxH|..."
            images = _parse_images(images_raw)

            posts.append(PostData(
                url=url,
                title=display_title,
                content=content or display_title,
                likes=up_count,
                comments_count=comment_count,
                author_name=username,
                published_at=published_at,
                images=images,
            ))
        except Exception:
            logger.exception(f"108community: error parsing item {item[:4]}")
            continue

    return posts


def _extract_title_from_content(content: str) -> str:
    """Extract a short title from a long content body."""
    if not content:
        return ""
    content = content.strip()
    # Try to use the first line or first sentence
    for sep in ["\n", "。", "！", "？", ".", "!", "?"]:
        idx = content.find(sep)
        if idx > 0:
            return content[:idx].strip()
    # Truncate
    return content[:80] + ("..." if len(content) > 80 else "")


def _parse_images(images_raw: str) -> list[str]:
    """Parse the pipe-separated image field into a list of URL strings.

    Format: "imageId,/user/YYYY/MMDD/filename.thumb.jpg,idx,WxH|..."
    We extract the path (index 1) and prepend the CDN base.
    """
    if not images_raw:
        return []

    result = []
    for entry in images_raw.split("|"):
        parts = entry.split(",")
        if len(parts) >= 2 and parts[1]:
            # parts[1] looks like "/user/2026/0714/filename.thumb.jpg"
            # Replace .thumb with full size
            img_path = parts[1].replace(".thumb.", ".")
            # Build full URL via photoshow CDN (same as the site uses)
            full_url = f"https://photoshow.108sq.cn{img_path}"
            result.append(full_url)

    return result[:5]  # Max 5 images per post


# Keep the old class for backward compatibility with monitor.py
# but it's no longer used by sentiment search.
class Tiantai108Crawler:
    """DEPRECATED: Use search_108community() instead.

    Playwright-based crawler kept only for backward compatibility
    with the crawlers router. Sentiment search now uses the JSONP API.
    """

    BASE_URL = "https://tiantai.108sq.cn"

    async def crawl(self, account_url: str) -> CrawlResult:
        return CrawlResult(success=False, error_message="crawl() not supported for 108community")

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        return await search_108community(keyword, limit)

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        return []
