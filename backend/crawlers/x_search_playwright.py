# intel-monitor/backend/crawlers/x_search_playwright.py
"""
X Search Playwright Fallback Crawler

Playwright headless 降级方案：持久化 profile 复用登录态，
直接调用 X GraphQL SearchTimeline API 进行搜索，以及 TweetDetail API 抓取评论。
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from crawlers.base import CrawlResult, PostData, CommentData

logger = logging.getLogger(__name__)

# X GraphQL constants
SEARCH_TIMELINE_QUERY_ID = "Yw6L66Pw54NHKuq4Dp7b4Q"
TWEET_DETAIL_QUERY_ID = "nBS-WpgA6ZG0CyNHD517JQ"
TWITTER_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

SEARCH_FEATURES = {
    "rweb_video_screen_enabled": True,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

SEARCH_FIELD_TOGGLES = {
    "withPayments": True,
    "withAuxiliaryUserLabels": True,
    "withArticleRichContentState": True,
    "withArticlePlainText": True,
    "withArticleSummaryText": True,
    "withArticleVoiceOver": True,
    "withGrokAnalyze": True,
    "withDisallowedReplyControls": True,
}

_COMMENT_FEATURES = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
}

_COMMENT_FIELD_TOGGLES = {"withArticleRichContentState": True, "withArticlePlainText": False}


async def search_x_via_playwright(keyword: str, limit: int = 20) -> CrawlResult:
    """
    Search X via Playwright headless with persistent profile.
    Requires the user to have logged into X once in a non-headless session.
    """
    from playwright.async_api import async_playwright

    user_data_dir = Path("backend/data/x_profile")
    user_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=True,
                args=["--no-sandbox"],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            try:
                # 1. Get ct0 cookie from persistent profile
                cookies = await context.cookies("https://x.com")
                ct0 = None
                for c in cookies:
                    if c["name"] == "ct0":
                        ct0 = c["value"]
                        break

                if not ct0:
                    # Try navigating to x.com to refresh cookies
                    await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=15000)
                    cookies = await context.cookies("https://x.com")
                    for c in cookies:
                        if c["name"] == "ct0":
                            ct0 = c["value"]
                            break

                if not ct0:
                    return CrawlResult(
                        success=False,
                        error_message="X 未登录。请先在非 headless 模式执行 opencli twitter search，完成登录后再试。"
                    )

                # 2. Fetch via SearchTimeline GraphQL
                tweets = await _fetch_search_timeline(page, ct0, keyword, limit)

                if not tweets:
                    return CrawlResult(
                        success=False,
                        error_message=f"未搜索到 X 关于 '{keyword}' 的内容"
                    )

                # 3. Convert to PostData
                posts = [_parse_tweet_to_postdata(t) for t in tweets]
                posts = [p for p in posts if p is not None]

                # 4. Fetch comments for each post
                await _fetch_comments_for_posts(page, ct0, posts)

                return CrawlResult(posts=posts, success=True)

            finally:
                await context.close()

    except Exception as e:
        logger.exception("X Playwright search error")
        return CrawlResult(success=False, error_message=str(e))


async def _fetch_search_timeline(page, ct0: str, keyword: str, limit: int) -> list[dict]:
    """Fetch tweets via X SearchTimeline GraphQL API."""
    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "X-Csrf-Token": ct0,
        "X-Twitter-Auth-Type": "OAuth2Session",
        "X-Twitter-Active-User": "yes",
        "Content-Type": "application/json",
    }

    all_tweets = []
    cursor = None
    seen = set()
    max_pages = 20

    for _ in range(max_pages):
        if len(all_tweets) >= limit:
            break

        vars_payload = {
            "rawQuery": keyword,
            "count": limit - len(all_tweets) + 10,
            "querySource": "typed_query",
            "product": "Top",
        }
        if cursor:
            vars_payload["cursor"] = cursor

        url = (
            f"https://x.com/i/api/graphql/{SEARCH_TIMELINE_QUERY_ID}/SearchTimeline"
            f"?variables={json.dumps(vars_payload)}"
            f"&features={json.dumps(SEARCH_FEATURES)}"
            f"&fieldToggles={json.dumps(SEARCH_FIELD_TOGGLES)}"
        )

        data = await page.evaluate("""
            async ([url, headers]) => {
                const resp = await fetch(url, {
                    method: 'GET',
                    headers: headers,
                    credentials: 'include',
                });
                if (!resp.ok) return { error: resp.status };
                return await resp.json();
            }
        """, [url, headers])

        if data.get("error"):
            logger.warning(f"X SearchTimeline returned HTTP {data['error']}")
            break

        new_tweets, cursor = _parse_search_timeline(data, seen)
        if not new_tweets:
            break

        all_tweets.extend(new_tweets)
        if not cursor:
            break

    return all_tweets[:limit]


def _parse_search_timeline(data, seen: set) -> tuple[list[dict], str | None]:
    """Parse SearchTimeline response. Returns (tweets, next_cursor)."""
    instructions = (
        data.get("data", {})
        .get("search_by_raw_query", {})
        .get("search_timeline", {})
        .get("timeline", {})
        .get("instructions", [])
    )

    tweets = []
    next_cursor = None

    def visit(value):
        nonlocal next_cursor
        if not value or not isinstance(value, (dict, list)):
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return

        # Extract tweet
        tw_result = value.get("tweet_results", {})
        if tw_result:
            result = tw_result.get("result", {})
            if result:
                tw = result.get("tweet", result) if result.get("__typename") == "TweetWithVisibilityResults" else result
                rest_id = tw.get("rest_id", "")
                if rest_id and rest_id not in seen:
                    seen.add(rest_id)
                    tweets.append(tw)

        # Extract cursor
        entry_type = value.get("entryType", "") or value.get("__typename", "")
        if "TimelineTimelineCursor" in entry_type:
            cursor_type = value.get("cursorType", "")
            if cursor_type in ("Bottom", "ShowMore") and value.get("value"):
                next_cursor = value["value"]

        for child in value.values():
            visit(child)

    for inst in instructions:
        visit(inst)

    return tweets, next_cursor


def _parse_tweet_to_postdata(tweet: dict) -> PostData | None:
    """Convert a raw X GraphQL tweet object to PostData."""
    try:
        legacy = tweet.get("legacy", {})
        if not legacy:
            return None

        user_result = tweet.get("core", {}).get("user_results", {}).get("result", {})
        user_legacy = user_result.get("legacy", {})

        author_screen_name = (
            user_result.get("core", {}).get("screen_name", "")
            or user_legacy.get("screen_name", "")
            or "unknown"
        )
        rest_id = tweet.get("rest_id", "")
        url = f"https://x.com/{author_screen_name}/status/{rest_id}" if rest_id else ""

        # Parse created_at
        published_at = None
        created_at_str = legacy.get("created_at", "")
        if created_at_str:
            try:
                published_at = datetime.strptime(
                    created_at_str, "%a %b %d %H:%M:%S %z %Y"
                ).replace(tzinfo=None)
            except Exception:
                pass

        # Extract media
        images = []
        media = legacy.get("extended_entities", {}).get("media", []) or legacy.get("entities", {}).get("media", [])
        for m in media:
            if m.get("type") == "photo" and m.get("media_url_https"):
                images.append(m["media_url_https"])
            elif m.get("type") in ("video", "animated_gif"):
                if m.get("media_url_https"):
                    images.append(m["media_url_https"])

        # Extract quoted tweet
        quoted_tweet = None
        if legacy.get("is_quote_status") and tweet.get("quoted_status_result"):
            q_result = tweet["quoted_status_result"].get("result", {})
            if q_result:
                q_tweet = q_result.get("tweet", q_result)
                q_legacy = q_tweet.get("legacy", {})
                q_user = q_tweet.get("core", {}).get("user_results", {}).get("result", {})
                q_user_legacy = q_user.get("legacy", {})
                if q_tweet.get("rest_id") and q_legacy.get("full_text"):
                    quoted_tweet = {
                        "id": q_tweet["rest_id"],
                        "author": q_user_legacy.get("screen_name", ""),
                        "name": q_user_legacy.get("name", ""),
                        "text": q_legacy.get("full_text", ""),
                        "created_at": q_legacy.get("created_at", ""),
                        "url": f"https://x.com/{q_user_legacy.get('screen_name', '')}/status/{q_tweet['rest_id']}",
                    }

        # Extract card
        card = None
        card_legacy = tweet.get("card", {}).get("legacy", {})
        if card_legacy and card_legacy.get("name"):
            bindings = card_legacy.get("binding_values", [])
            bv = {}
            for b in bindings:
                if b.get("key") and b.get("value"):
                    bv[b["key"]] = b["value"]

            card_title = bv.get("title", {}).get("string_value", "")
            card_desc = bv.get("description", {}).get("string_value", "")
            card_url = bv.get("card_url", {}).get("string_value", "")
            domain = bv.get("domain", {}).get("string_value", "")

            if card_title or card_desc or card_url:
                card = {"title": card_title, "description": card_desc, "url": card_url, "domain": domain}

        return PostData(
            url=url,
            content=legacy.get("full_text", ""),
            likes=legacy.get("favorite_count", 0) or 0,
            views=int(tweet.get("views", {}).get("count", "0") or "0"),
            shares=legacy.get("retweet_count", 0) or 0,
            comments_count=legacy.get("reply_count", 0) or 0,
            bookmarks=legacy.get("bookmark_count", 0) or 0,
            author_name=user_legacy.get("name", "") or "",
            author_avatar=user_legacy.get("profile_image_url_https", "") or "",
            author_followers=0,
            published_at=published_at,
            images=images,
            quoted_tweet=quoted_tweet,
            card=card,
        )
    except Exception as e:
        logger.warning(f"Failed to parse tweet to PostData: {e}")
        return None


async def _fetch_comments_for_posts(page, ct0: str, posts: list[PostData], max_comments: int = 5):
    """Fetch top comments for each X post via TweetDetail GraphQL API."""
    if not posts:
        return

    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
        "X-Csrf-Token": ct0,
        "X-Twitter-Auth-Type": "OAuth2Session",
        "X-Twitter-Active-User": "yes",
    }

    for post in posts:
        try:
            tweet_id = _extract_tweet_id(post.url)
            if not tweet_id:
                continue

            vars_payload = {
                "focalTweetId": tweet_id,
                "referrer": "tweet",
                "with_rux_injections": False,
                "includePromotedContent": False,
                "rankingMode": "Recency",
                "withCommunity": True,
                "withQuickPromoteEligibilityTweetFields": True,
                "withBirdwatchNotes": True,
                "withVoice": True,
            }

            url = (
                f"https://x.com/i/api/graphql/{TWEET_DETAIL_QUERY_ID}/TweetDetail"
                f"?variables={json.dumps(vars_payload)}"
                f"&features={json.dumps(_COMMENT_FEATURES)}"
                f"&fieldToggles={json.dumps(_COMMENT_FIELD_TOGGLES)}"
            )

            data = await page.evaluate("""
                async ([url, headers]) => {
                    const resp = await fetch(url, {
                        method: 'GET',
                        headers: headers,
                        credentials: 'include',
                    });
                    if (!resp.ok) return { error: resp.status };
                    return await resp.json();
                }
            """, [url, headers])

            if data.get("error"):
                continue

            comments = _parse_tweet_detail_comments(data, tweet_id, max_comments)
            if comments:
                post.comments = comments

            await asyncio.sleep(0.5)  # Rate limit

        except Exception as e:
            logger.warning(f"X comment fetch error for {post.url}: {e}")
            continue


def _extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from X URL."""
    if not url:
        return None
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else None


def _parse_tweet_detail_comments(data: dict, own_tweet_id: str, max_comments: int = 5) -> list[CommentData]:
    """Parse TweetDetail response to extract top-level replies."""
    instructions = (
        data.get("data", {})
        .get("threaded_conversation_with_injections_v2", {})
        .get("instructions", [])
    )

    replies = []
    for inst in instructions:
        for entry in inst.get("entries", []):
            content = entry.get("content", {})
            items = content.get("items", [])
            for item in items:
                tweet_result = (
                    item.get("item", {})
                    .get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", {}) or {}
                if not tweet_result:
                    continue

                rest_id = tweet_result.get("rest_id", "")
                if rest_id == own_tweet_id:
                    continue

                legacy = tweet_result.get("legacy", {})
                if not legacy or not legacy.get("full_text"):
                    continue

                user_result = tweet_result.get("core", {}).get("user_results", {}).get("result", {})
                author = user_result.get("legacy", {}).get("screen_name", "")
                likes = legacy.get("favorite_count", 0)

                replies.append(CommentData(text=legacy["full_text"], author=author, likes=likes))

    replies.sort(key=lambda c: c.likes, reverse=True)
    return replies[:max_comments]
