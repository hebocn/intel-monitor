# intel-monitor/backend/crawlers/facebook_cse_search.py
"""
Facebook search via Google Custom Search Engine (CSE) + Playwright.

Uses Google CSE to search Facebook content, then clicks into public text posts
(/posts/) to extract full content, interaction data, and comments.

Video (/videos/) and photo (/photos/) posts are skipped as they require
Facebook login.

Architecture: independent async function (like YouTube search), wrapped via
_run_crawler_in_thread() for Windows Playwright compatibility.
"""

import asyncio
import logging
import re
import sys
from datetime import datetime
from urllib.parse import quote, urlparse

from crawlers.base import CrawlResult, PostData, CommentData

logger = logging.getLogger(__name__)

# Google CSE ID for Facebook search — configured via GOOGLE_CSE_ID env var
CSE_ID = "016621447308871563343:vylfmzjmlti"

CSE_URL_TEMPLATE = (
    "https://cse.google.com/cse?cx={cse_id}"
    "#gsc.tab=0&gsc.q={keyword}&gsc.sort="
)


def _get_cse_id() -> str:
    """Read CSE ID from config, falling back to the default."""
    try:
        from config import settings
        return settings.GOOGLE_CSE_ID or CSE_ID
    except Exception:
        return CSE_ID


async def search_facebook(keyword: str, limit: int = 20) -> CrawlResult:
    """Search Facebook via Google CSE and extract post details.

    Args:
        keyword: Search keyword.
        limit: Max posts to return (applied after filtering to /posts/ type).

    Returns:
        CrawlResult with PostData entries; success=False on failure.
    """
    from playwright.async_api import async_playwright

    cse_id = _get_cse_id()
    search_url = CSE_URL_TEMPLATE.format(cse_id=cse_id, keyword=quote(keyword))

    playwright = None
    browser = None

    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        page = await browser.new_page()

        # ── Step 1: Load CSE search results ──────────────────────────
        logger.info(f"Facebook CSE: navigating to search page for '{keyword}'")
        await page.goto(search_url, wait_until="networkidle", timeout=30000)

        # Wait for search results to render (CSE loads via JS)
        await page.wait_for_selector(".gsc-webResult, .gsc-result, .gsc-expansionArea", timeout=15000)

        # Give JS a moment to finish rendering
        await asyncio.sleep(2)

        # Extract results from the page
        results = await page.evaluate("""() => {
            const items = [];
            const containers = document.querySelectorAll('.gsc-webResult, .gsc-result');
            containers.forEach((container) => {
                const titleEl = container.querySelector('.gs-title a, a.gs-title');
                const snippetEl = container.querySelector('.gs-snippet');
                const visibleUrlEl = container.querySelector('.gs-visibleUrl');

                const title = titleEl ? titleEl.textContent.trim() : '';
                const url = titleEl ? (titleEl.getAttribute('href') || titleEl.href || '') : '';
                const snippet = snippetEl ? snippetEl.textContent.trim() : '';
                const visibleUrl = visibleUrlEl ? visibleUrlEl.textContent.trim() : '';

                if (title && url) {
                    let type = 'post';
                    if (url.indexOf('/videos/') >= 0) type = 'video';
                    else if (url.indexOf('/photos/') >= 0 || url.indexOf('media/set') >= 0) type = 'photo';
                    else if (url.indexOf('/groups/') >= 0) type = 'group';
                    else if (url.indexOf('/posts/') < 0 && url.indexOf('/videos/') < 0 &&
                             url.indexOf('/photos/') < 0 && url.indexOf('/media/') < 0) type = 'profile';

                    items.push({ title, url, snippet, visibleUrl, type });
                }
            });
            return items;
        }""")

        if not results:
            logger.warning(f"Facebook CSE: no results found for '{keyword}'")
            return CrawlResult(success=True, posts=[], error_message="No results found")

        logger.info(f"Facebook CSE: found {len(results)} search results for '{keyword}'")

        # ── Step 2: Filter and click into text posts ──────────────────
        posts = []
        error_count = 0

        for item in results:
            if len(posts) >= limit:
                break

            url = item["url"]
            item_type = item["type"]

            # Skip non-post types
            if item_type != "post":
                logger.debug(f"Facebook CSE: skipping {item_type}: {item['title'][:60]}")
                continue

            try:
                post_data = await _fetch_post_detail(
                    browser, url, item["title"], item["snippet"]
                )
                if post_data:
                    posts.append(post_data)
                    logger.info(f"Facebook CSE: extracted post {len(posts)}/{limit}: {item['title'][:60]}")
            except Exception as e:
                error_count += 1
                logger.warning(f"Facebook CSE: failed to fetch post {url}: {e}")
                # Still add a partial result with what we have from CSE snippet
                posts.append(PostData(
                    url=url,
                    title=item["title"],
                    content=item["snippet"],
                ))

        logger.info(
            f"Facebook CSE: completed — {len(posts)} posts extracted, "
            f"{error_count} errors, {len(results)} total results"
        )

        return CrawlResult(
            success=True,
            posts=posts,
            error_message=f"{error_count} fetch errors" if error_count else "",
        )

    except Exception as e:
        logger.exception(f"Facebook CSE search error: {e}")
        return CrawlResult(success=False, error_message=str(e))

    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass


async def _fetch_post_detail(
    browser, url: str, fallback_title: str, fallback_snippet: str
) -> PostData | None:
    """Open a Facebook post in a new tab and extract content + interactions.

    Uses a new page (tab) in the existing browser context. Closes the tab
    after extraction to keep resource usage low.
    """
    page = await browser.new_page()

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)

        # Wait briefly for content to load
        await asyncio.sleep(2)

        # Check for login wall
        login_detected = await page.evaluate("""() => {
            const body = document.body ? document.body.innerText : '';
            return body.indexOf('上 Facebook 查看更多内容') >= 0 ||
                   body.indexOf('See more on Facebook') >= 0 ||
                   body.indexOf('Log into Facebook') >= 0 ||
                   body.indexOf('登录 Facebook') >= 0;
        }""")

        if login_detected:
            logger.debug(f"Facebook CSE: login wall detected for {url}")
            return PostData(
                url=url,
                title=fallback_title,
                content=fallback_snippet,
            )

        # Extract post data from the rendered dialog
        data = await page.evaluate("""() => {
            const dialog = document.querySelector('[role="dialog"]');
            if (!dialog) return null;

            // Get innerText (preserves line breaks)
            const innerText = dialog.innerText || '';
            const textContent = dialog.textContent || '';

            return {
                innerText: innerText.substring(0, 8000),
                textContent: textContent.substring(0, 8000),
            };
        }""")

        if not data:
            return PostData(
                url=url,
                title=fallback_title,
                content=fallback_snippet,
            )

        inner_text = data.get("innerText", "")
        text_content = data.get("textContent", "")

        # Parse metrics — use innerText which preserves structure
        likes = _parse_reactions(inner_text)
        comments_count = _parse_metric(inner_text, r'(\d[\d,]*)\s*条评论')
        if comments_count == 0:
            comments_count = _parse_metric(inner_text, r'(\d[\d,]*)\s*comment')
        shares = _parse_metric(inner_text, r'(\d[\d,]*)\s*次分享')
        if shares == 0:
            shares = _parse_metric(inner_text, r'(\d[\d,]*)\s*share')

        # Extract author — first line of dialog is usually "XXX的帖子"
        author = ""
        lines = [l.strip() for l in inner_text.split("\n") if l.strip()]
        for line in lines:
            # Pattern: "AuthorName的帖子" or "Author Name的帖子"
            m = re.match(r'^(.+?)的(帖子|视频|照片|相册)$', line)
            if m:
                author = m.group(1).strip()
                break

        # Extract date
        published_at = None
        date_match = re.search(
            r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', inner_text
        )
        if date_match:
            try:
                y, m_num, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                published_at = datetime(y, m_num, d)
            except ValueError:
                pass

        # Also try "X月X日" (current year implied)
        if not published_at:
            date_match2 = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', inner_text)
            if date_match2:
                try:
                    m_num, d = int(date_match2.group(1)), int(date_match2.group(2))
                    published_at = datetime(datetime.now().year, m_num, d)
                except ValueError:
                    pass

        # Build title: first meaningful line of the post content (skip metadata)
        metadata_prefixes = [
            "的帖子", "的視頻", "的照片", "的相册",
            "分钟", "小时", "天", "周", "年",
            "分享对象", "所有心情", "条评论", "次分享",
            "最相关", "条回复", "个心情",
        ]
        title = fallback_title
        for line in lines:
            # Skip lines that are clearly metadata
            if not line or len(line) < 5:
                continue
            if any(prefix in line for prefix in metadata_prefixes):
                continue
            if re.match(r'^\d[\d,]*$', line):  # Just a number
                continue
            if re.match(r'^(赞|评论|分享|查看|全部)', line):
                continue
            # Found the first content line
            title = line[:120]
            break

        # Content: use full text, trim to reasonable size
        # Strip out repeated metadata from content for cleanliness
        content = inner_text
        # Truncate at comment section for cleaner content
        comment_marker = re.search(r'\n所有心情[：:]', content)
        if not comment_marker:
            comment_marker = re.search(r'\n最相关\n', content)
        if not comment_marker:
            comment_marker = re.search(r'\n赞\n评论\n', content)

        if comment_marker:
            # Keep pre-comments part as body, post-comments as separate
            body_text = content[:comment_marker.start()].strip()
            comments_section = content[comment_marker.start():].strip()
        else:
            body_text = content
            comments_section = ""

        content = body_text[:3000]

        # Extract comments
        comments = _extract_comments(inner_text) if comments_section else []

        return PostData(
            url=url,
            title=title,
            content=content,
            likes=likes,
            comments_count=comments_count,
            shares=shares,
            views=0,
            bookmarks=0,
            author_name=author,
            published_at=published_at,
            comments=comments,
        )

    except Exception as e:
        logger.warning(f"Facebook CSE: error fetching detail for {url}: {e}")
        return PostData(
            url=url,
            title=fallback_title,
            content=fallback_snippet,
        )

    finally:
        try:
            await page.close()
        except Exception:
            pass


def _parse_reactions(text: str) -> int:
    """Parse total Facebook reaction count from dialog text.

    Handles patterns like:
    - "所有心情： 2,406"
    - "2,406"
    - "赞：1,727位用户" (just likes)
    """
    # Pattern 1: "所有心情：" followed by number
    m = re.search(r'所有心情[：:]\s*([\d,]+)', text)
    if m:
        return int(m.group(1).replace(",", ""))

    # Pattern 2: button with reactions count (e.g. "赞：1,727位用户")
    # Sum up all "X位用户" patterns that appear near reaction buttons
    total = 0
    for m in re.finditer(r'([\d,]+)\s*位用户', text):
        try:
            total += int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    if total > 0:
        return total

    # Pattern 3: standalone number after "赞" or reaction row
    m = re.search(r'赞[：:]\s*([\d,]+)', text)
    if m:
        return int(m.group(1).replace(",", ""))

    return 0


def _parse_metric(text: str, pattern: str) -> int:
    """Parse a metric like '1,122条评论' or '135次分享' from text."""
    m = re.search(pattern, text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0


def _extract_comments(text: str, max_comments: int = 10) -> list[CommentData]:
    """Extract top-level comments from Facebook post dialog text.

    Comments appear as: AuthorName CommentText N周/N天/N小时 N个心情
    Skips sub-replies (which start with "   AuthorName" or are indented).
    """
    comments = []

    # Split into lines and parse comment blocks
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Find comment section start
    comment_start = -1
    for i, line in enumerate(lines):
        if line == "最相关" or line == "Most relevant":
            comment_start = i
            break
    if comment_start < 0:
        for i, line in enumerate(lines):
            if "条评论" in line or "comments" in line.lower():
                comment_start = i
                break

    if comment_start < 0:
        return comments

    i = comment_start + 1
    current_author = None
    current_text_parts = []

    while i < len(lines) and len(comments) < max_comments:
        line = lines[i]

        # Skip UI elements
        if line in ("赞", "评论", "分享", "Like", "Comment", "Share", "全部", "查看"):
            i += 1
            continue

        # Skip reply/action lines
        if re.match(r'^(全部\d+条回复|查看\d+条回复|\d+个心情|View)', line):
            i += 1
            continue

        # Time marker: "45周", "2天前", "3小时", etc. — end of a comment
        has_time = re.search(r'\d+\s*(周|天|小时|分钟|d|w|h|m)s?\b', line)

        # New comment: line is a short name (2-15 chars, no spaces typically for Chinese names,
        # or a Facebook name with Latin chars)
        is_name = (
            len(line) >= 2 and len(line) <= 30
            and not re.search(r'[\d,，。！？!?]{3,}', line)
            and line not in ("最相关", "Most relevant", "正在加载", "Loading")
        )

        if is_name and not has_time and not current_author:
            # Start of a new comment
            current_author = line
            current_text_parts = []
        elif current_author:
            if has_time:
                # End of this comment
                comment_text = " ".join(current_text_parts).strip()
                if comment_text and len(comment_text) > 1:
                    comments.append(CommentData(
                        text=comment_text[:500],
                        author=current_author,
                        likes=0,
                    ))
                current_author = None
                current_text_parts = []
            else:
                current_text_parts.append(line)

        i += 1

    # Don't forget the last comment
    if current_author and current_text_parts:
        comment_text = " ".join(current_text_parts).strip()
        if comment_text and len(comment_text) > 1:
            comments.append(CommentData(
                text=comment_text[:500],
                author=current_author,
                likes=0,
            ))

    return comments[:max_comments]
