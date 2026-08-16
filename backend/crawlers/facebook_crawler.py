# intel-monitor/backend/crawlers/facebook_crawler.py
"""
Facebook 账号监测爬虫 — Google CSE + headless Playwright,不依赖登录态。

把 Facebook 账号加为监测目标后,用 Google CSE 搜索该账号被 Google 索引的
帖子,逐条进 /posts/ 详情页提取正文与互动数据(登录墙帖自动降级为 CSE 摘要)。

与 facebook_cse_search.py 的关系:
- facebook_cse_search.py  = 舆情模块的关键词 → 帖子搜索(search_facebook)
- 本模块                   = 监测模块的账号 → 帖子搜索(FacebookCrawler.crawl)
- 共用 CSE 搜索基建(CSE_URL_TEMPLATE / _get_cse_id)与 _fetch_post_detail 详情解析

固有限制(CSE 模式):
- 只能监测 Google 已索引的帖子,新帖滞后(天~周级),不实时
- 未登录访问 Facebook 主页时间线受限,详情页遇登录墙只有 CSE 摘要、无互动数据
"""

import asyncio
import logging
from urllib.parse import parse_qs, urlparse

from crawlers.base import CrawlResult, PostData, CommentData, PlaywrightCrawler
from crawlers.facebook_cse_search import (
    CSE_URL_TEMPLATE,
    _get_cse_id,
    _fetch_post_detail,
)

logger = logging.getLogger(__name__)

# CSE 结果里允许出现的 Facebook 域名变体(去掉协议与子域后都归一化到 facebook.com)
_FB_HOST_ALIASES = ("www.facebook.com", "web.facebook.com", "m.facebook.com", "mbasic.facebook.com", "touch.facebook.com", "facebook.com", "fb.com")
_ACCOUNT_PATH_PREFIXES = ("/posts/", "/videos/", "/photos/", "/reel/", "/permalink.php", "/photo.php", "/video.php", "/media/set", "/groups/", "/profile.php")


# ── URL 工具 ──────────────────────────────────────────────────────────────


def _normalize_fb_url(url: str) -> str:
    """归一化 Facebook URL:去协议、去子域变体,返回 'facebook.com{path}?{query}'."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else "//" + url)
    host = (parsed.hostname or "").lower()
    for alias in _FB_HOST_ALIASES:
        if host == alias or host.endswith("." + alias):
            host = "facebook.com"
            break
    if host != "facebook.com":
        return ""
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"facebook.com{path}{query}"


def _classify_url(url: str) -> str:
    """把 Facebook URL 分类为 post / video / photo / group / profile."""
    norm = _normalize_fb_url(url)
    if not norm:
        return "other"
    if "/videos/" in norm or norm.startswith("facebook.com/video.php"):
        return "video"
    if "/photos/" in norm or "media/set" in norm or norm.startswith("facebook.com/photo.php"):
        return "photo"
    if "/groups/" in norm:
        return "group"
    # 帖子:路径 /posts/ 或 permalink/photo/video 详情页(query 带 story_fbid / fbid)
    if "/posts/" in norm or norm.startswith("facebook.com/permalink.php") or "story_fbid" in norm or "fbid" in norm:
        return "post"
    if norm.startswith("facebook.com/profile.php"):
        return "profile"
    if norm.startswith("facebook.com/"):
        # 其它路径(如 /username)视为主页
        return "profile"
    return "other"


def _parse_account(account_url: str) -> tuple[str, str]:
    """从账号 URL 解析出 (handle, account_id)。数字 ID 账号返回 ('', id)。"""
    norm = _normalize_fb_url(account_url)
    if not norm:
        return "", ""
    if norm.startswith("facebook.com/profile.php"):
        qs = parse_qs(urlparse(account_url).query)
        return "", qs.get("id", [""])[0]
    path = norm.removeprefix("facebook.com").lstrip("/")
    handle = path.split("/")[0].strip()
    if not handle or handle.lower() in ("home", "login", "pages"):
        return "", ""
    return handle, ""


def _matches_account(norm_url: str, handle: str, account_id: str) -> bool:
    """判断归一化后的 URL 是否属于目标账号(handle 前缀 或 数字 ID query)."""
    if not norm_url:
        return False
    if handle:
        # username 型:facebook.com/{handle}/... 或 facebook.com/{handle}(主页本身)
        if norm_url == f"facebook.com/{handle}":
            return True
        if norm_url.startswith(f"facebook.com/{handle}/"):
            return True
        # 其它路径形式不能匹配(如 posts 页带不同路径段) — 上面的前缀已覆盖
    if account_id:
        qs = parse_qs(urlparse(norm_url.replace("facebook.com", "https://facebook.com")).query)
        if qs.get("id") == [account_id]:
            return True
        if qs.get("story_fbid") and qs.get("id") == [account_id]:
            return True
    return False


def _extract_items_js() -> str:
    """CSE 结果页 DOM 提取 JS — 返回 {title,url,snippet,visibleUrl} 列表."""
    return """() => {
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
            if (title && url) items.push({ title, url, snippet, visibleUrl });
        });
        return items;
    }"""


async def _cse_search(browser, keyword: str, max_pages: int = 2) -> list[dict]:
    """用 CSE 搜索关键词,翻页合并去重,返回原始结果 items 列表."""
    cse_id = _get_cse_id()
    search_url = CSE_URL_TEMPLATE.format(cse_id=cse_id, keyword=keyword)
    page = await browser.new_page()
    seen_urls: set[str] = set()
    all_items: list[dict] = []

    try:
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        try:
            await page.wait_for_selector(".gsc-webResult, .gsc-result, .gsc-expansionArea", timeout=15000)
        except Exception:
            logger.warning(f"Facebook CSE: no result container for '{keyword}'")
            return []
        await asyncio.sleep(2)

        for page_idx in range(max_pages):
            raw = await page.evaluate(_extract_items_js())
            for item in raw:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_items.append(item)

            if page_idx == max_pages - 1:
                break

            # 翻页:点击 CSE 分页按钮(非当前页)
            clicked = await page.evaluate("""() => {
                const cursors = document.querySelectorAll('.gsc-cursor-page');
                if (cursors.length === 0) return false;
                for (const c of cursors) {
                    if (!c.classList.contains('gsc-cursor-current-page')) {
                        c.click();
                        return true;
                    }
                }
                return false;
            }""")
            if not clicked:
                break
            await asyncio.sleep(2.5)

        logger.info(f"Facebook CSE: '{keyword}' -> {len(all_items)} raw results")
        return all_items
    except Exception as e:
        logger.warning(f"Facebook CSE: search error for '{keyword}': {e}")
        return all_items
    finally:
        try:
            await page.close()
        except Exception:
            pass


# ── 昵称反查:候选账号列表(供添加目标时点选) ─────────────────────────────


async def search_facebook_accounts(nickname: str, limit: int = 8) -> list[dict]:
    """按昵称用 CSE 搜索,返回 facebook 主页候选列表。

    过滤规则:CSE 结果里域名必须是 facebook.com(变体已归一化),且类型为
    profile(不含 /posts/ 等帖子路径)。翻 2 页补召回,按 URL 去重。
    """
    from playwright.async_api import async_playwright

    playwright = None
    browser = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )

        items = await _cse_search(browser, nickname, max_pages=2)

        candidates: list[dict] = []
        seen: set[str] = set()
        for item in items:
            if len(candidates) >= limit:
                break
            norm = _normalize_fb_url(item.get("url", ""))
            if not norm:
                continue
            if _classify_url(norm) != "profile":
                continue
            if norm in seen:
                continue
            seen.add(norm)
            candidates.append({
                "nickname": item.get("title", "").split(" | ")[0].strip() or item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", "")[:200],
            })

        logger.info(f"Facebook account search: '{nickname}' -> {len(candidates)} candidates")
        return candidates[:limit]
    except Exception as e:
        logger.exception(f"Facebook account search error for '{nickname}': {e}")
        return []
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


# ── 监测爬虫:账号 → 帖子 ─────────────────────────────────────────────────


class FacebookCrawler(PlaywrightCrawler):
    """Facebook 账号监测爬虫。crawl(account_url) 抓取该账号被索引的帖子。"""

    platform = "facebook"

    async def crawl(self, account_url: str) -> CrawlResult:
        handle, account_id = _parse_account(account_url)
        if not handle and not account_id:
            return CrawlResult(
                success=False,
                error_message=f"无法解析 Facebook 账号 URL: {account_url}",
            )

        await self.init_browser()
        try:
            # 组合查询:CSE 不支持 site: 操作符,只能在结果端按 URL 前缀过滤。
            # 主查询用 'facebook.com/{handle}' 召回该账号页面,兜底查询用 handle 本身。
            queries: list[str] = []
            if handle:
                queries.append(f"facebook.com/{handle}")
                queries.append(handle)
            else:
                queries.append(account_id)

            seen_urls: set[str] = set()
            raw_items: list[dict] = []
            for q in queries:
                items = await _cse_search(self.browser, q, max_pages=2)
                for item in items:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        raw_items.append(item)

            if not raw_items:
                logger.warning(f"Facebook: no CSE results for account '{handle or account_id}'")
                return CrawlResult(success=True, posts=[], error_message="CSE 未索引到该账号内容")

            # 过滤:只保留属于该账号的帖子类 URL(主页本身不算帖子)
            posts: list[PostData] = []
            for item in raw_items:
                if len(posts) >= 10:
                    break
                norm = _normalize_fb_url(item.get("url", ""))
                if not norm or not _matches_account(norm, handle, account_id):
                    continue
                if _classify_url(norm) != "post":
                    continue
                try:
                    post_data = await _fetch_post_detail(
                        self.browser, item["url"], item.get("title", ""), item.get("snippet", "")
                    )
                    if post_data:
                        posts.append(post_data)
                except Exception as e:
                    logger.warning(f"Facebook: failed to fetch post {item['url']}: {e}")
                    posts.append(PostData(
                        url=item["url"],
                        title=item.get("title", ""),
                        content=item.get("snippet", ""),
                    ))

            logger.info(
                f"Facebook monitor: {handle or account_id} -> {len(posts)} posts "
                f"from {len(raw_items)} raw results"
            )
            return CrawlResult(success=True, posts=posts)
        finally:
            await self.close()

    async def get_hot_comments(self, post_url: str) -> list[CommentData]:
        """headless 无登录态,Facebook 评论不可靠抓取 — 返回空列表(前端提示不支持)。"""
        logger.info(f"Facebook: comments not supported in headless mode: {post_url[-30:]}")
        return []
