# intel-monitor/backend/crawlers/youtube_search.py
"""
YouTube keyword search via YouTube Data API v3.

Two-step approach:
1. search.list   → video IDs + basic snippet (title, channel, thumbnail)
2. videos.list   → statistics (views, likes, comments) + full description + duration

Quota: search.list = 100 units, videos.list = 1-2 units. Daily budget 10,000.
"""
import logging
from datetime import datetime
from urllib.parse import quote

import httpx

from config import settings
from crawlers.base import CrawlResult, PostData

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


async def _youtube_get(path: str, params: dict) -> dict | None:
    """Make an authenticated YouTube Data API GET request."""
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        return None

    params = params | {"key": api_key}
    url = f"{YOUTUBE_API_BASE}{path}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def search_youtube(keyword: str, limit: int = 20) -> CrawlResult:
    """Search YouTube for videos matching keyword.

    Returns CrawlResult with PostData entries containing:
      - title, content (description), published_at, url
      - author_name (channel title), author_avatar (channel thumbnail)
      - views, likes, comments_count
      - images (video thumbnail)
      - content prefixed with duration (e.g. "[⏱ 12:34] description...")
    """
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        return CrawlResult(success=False, error_message="YouTube API Key 未配置，请在系统设置中填写")

    limit = min(max(limit, 1), 50)

    # Step 1: search.list
    try:
        search_data = await _youtube_get("/search", {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": limit,
            "order": "relevance",
            "relevanceLanguage": "zh",
        })
        if not search_data:
            return CrawlResult(success=False, error_message="YouTube API Key 未配置")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            try:
                body = e.response.json()
                reason = body.get("error", {}).get("errors", [{}])[0].get("reason", "")
            except Exception:
                reason = ""
            if reason == "quotaExceeded":
                return CrawlResult(success=False, error_message="YouTube API 日配额已用尽，请次日再试")
            return CrawlResult(success=False, error_message="YouTube API Key 无效或被限制")
        return CrawlResult(success=False, error_message=f"YouTube API 错误: HTTP {e.response.status_code}")
    except httpx.TimeoutException:
        return CrawlResult(success=False, error_message="YouTube API 请求超时")
    except Exception as e:
        logger.exception(f"YouTube search error for '{keyword}'")
        return CrawlResult(success=False, error_message=str(e))

    items = search_data.get("items", [])
    if not items:
        return CrawlResult(posts=[], success=True)

    # Map video_id → raw snippet for merging
    video_map: dict[str, dict] = {}
    for item in items:
        vid = item.get("id", {}).get("videoId", "")
        if vid:
            video_map[vid] = item.get("snippet", {})

    # Step 2: videos.list — get statistics + full description + duration
    video_ids = list(video_map.keys())
    statistics: dict[str, dict] = {}
    content_details: dict[str, dict] = {}

    try:
        if video_ids:
            video_data = await _youtube_get("/videos", {
                "part": "statistics,contentDetails,snippet",
                "id": ",".join(video_ids),
            })
            if video_data:
                for v in video_data.get("items", []):
                    vid = v.get("id", "")
                    statistics[vid] = v.get("statistics", {})
                    content_details[vid] = v.get("contentDetails", {})
                    # Also overwrite snippet with full version (untruncated description)
                    full_snippet = v.get("snippet", {})
                    if full_snippet:
                        video_map[vid] = full_snippet
    except Exception:
        logger.warning("YouTube videos.list failed, continuing with search.list snippets only")

    # Step 3: Build PostData entries
    posts = []
    for vid, snippet in video_map.items():
        try:
            title = (snippet.get("title") or "").strip()
            description = (snippet.get("description") or "").strip()
            channel_title = (snippet.get("channelTitle") or "").strip()
            published_at_str = snippet.get("publishedAt", "")
            thumbnails = snippet.get("thumbnails", {})

            # Publish time
            published_at = None
            if published_at_str:
                try:
                    published_at = datetime.strptime(
                        published_at_str.replace("Z", "+00:00"), "%Y-%m-%dT%H:%M:%S%z"
                    ).replace(tzinfo=None)  # naive UTC
                except ValueError:
                    pass

            # Statistics
            stats = statistics.get(vid, {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comment_count = int(stats.get("commentCount", 0))

            # Duration
            duration_text = ""
            dur = content_details.get(vid, {}).get("duration", "")
            if dur:
                duration_text = _parse_duration(dur)

            # Content with optional duration prefix
            if duration_text:
                content = f"[⏱ {duration_text}] {description}" if description else f"[⏱ {duration_text}]"
            else:
                content = description

            # Video URL
            url = f"https://www.youtube.com/watch?v={vid}"

            # Thumbnails as images (pick best quality → medium fallback)
            images = []
            for quality in ("maxres", "standard", "high", "medium", "default"):
                thumb = thumbnails.get(quality)
                if thumb and thumb.get("url"):
                    images.append(thumb["url"])
                    break

            posts.append(PostData(
                url=url,
                title=title,
                content=content,
                views=views,
                likes=likes,
                comments_count=comment_count,
                author_name=channel_title,
                published_at=published_at,
                images=images,
            ))
        except Exception:
            logger.exception(f"YouTube: error building PostData for video {vid}")
            continue

    logger.info(f"YouTube search '{keyword}': {len(posts)} videos")
    return CrawlResult(posts=posts, success=len(posts) > 0)


def _parse_duration(iso_duration: str) -> str:
    """Convert ISO 8601 duration to human-readable format.
    e.g. 'PT12M34S' → '12:34', 'PT1H2M3S' → '1:02:03'
    """
    import re

    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not m:
        return iso_duration

    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    s = int(m.group(3) or 0)

    if h > 0:
        return f"{h}:{mins:02d}:{s:02d}"
    return f"{mins}:{s:02d}"
