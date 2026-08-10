import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Platform -> (autocli site, autocli command)
PLATFORM_CMD: dict[str, tuple[str, str]] = {
    "weibo": ("weibo", "hot"),
    "zhihu": ("zhihu", "hot"),
    "bilibili": ("bilibili", "hot"),
    "v2ex": ("v2ex", "hot"),
    "hackernews": ("hackernews", "top"),
    "reddit": ("reddit", "hot"),
    "twitter": ("twitter", "trending"),  # Twitter/X only shows ~5 trending topics
    "douban_movie": ("douban", "movie-hot"),
    "douban_book": ("douban", "book-hot"),
    "xueqiu": ("xueqiu", "hot"),
    "linux-do": ("linux-do", "hot"),
    "bbc": ("bbc", "news"),
    "google_trends": ("google", "trends"),
    "stackoverflow": ("stackoverflow", "hot"),
    "github": ("github", "trending"),  # custom scraper, not autocli
}

PLATFORM_LABELS: dict[str, str] = {
    "weibo": "微博",
    "zhihu": "知乎",
    "bilibili": "B站",
    "v2ex": "V2EX",
    "hackernews": "HackerNews",
    "reddit": "Reddit",
    "twitter": "Twitter/X",
    "douban_movie": "豆瓣电影",
    "douban_book": "豆瓣图书",
    "xueqiu": "雪球",
    "linux-do": "Linux.do",
    "bbc": "BBC",
    "google_trends": "Google Trends",
    "stackoverflow": "StackOverflow",
    "github": "GitHub",
}

PLATFORM_MODES: dict[str, str] = {
    "weibo": "browser",
    "zhihu": "browser",
    "bilibili": "browser",
    "v2ex": "public",
    "hackernews": "public",
    "reddit": "public",
    "twitter": "browser",
    "douban_movie": "browser",
    "douban_book": "browser",
    "xueqiu": "browser",
    "linux-do": "public",
    "bbc": "public",
    "google_trends": "public",
    "stackoverflow": "public",
    "github": "public",
}


@dataclass
class TopicItem:
    title: str
    url: str = ""
    rank: int = 0
    hot_value: str = ""
    extra: dict = field(default_factory=dict)


def _normalize_topics(platform: str, raw_items: list[dict]) -> list[TopicItem]:
    """Normalize raw autocli JSON into TopicItem list."""
    topics = []
    for i, item in enumerate(raw_items):
        title = item.get("title") or item.get("word") or item.get("topic") or item.get("text") or item.get("name") or item.get("query") or ""
        if not title:
            continue

        url = item.get("url") or item.get("link") or ""
        rank = item.get("rank", i + 1)

        # Extract hot_value from various fields
        hot_value = ""
        for key in ("hot_value", "heat", "score", "rating", "hot", "likes", "replies", "comments", "views", "play"):
            if key in item and item[key]:
                hot_value = str(item[key])
                break

        # Build extra with remaining interesting fields
        skip_keys = {"title", "word", "topic", "text", "name", "query", "url", "link", "rank", "score", "hot", "heat",
                     "likes", "replies", "comments", "views", "play", "hot_value", "rating"}
        extra = {k: v for k, v in item.items() if k not in skip_keys and v}

        topics.append(TopicItem(
            title=title,
            url=url,
            rank=rank,
            hot_value=hot_value,
            extra=extra,
        ))
    return topics


# opencli installed via npm global; ensure its bin dir is on PATH for subprocess
import os as _os
_OPENCLI_CMD = "opencli.cmd" if _os.name == "nt" else "opencli"

def _run_autocli_sync(site: str, command: str, limit: int) -> tuple[int, str, str]:
    """Run opencli synchronously. Returns (returncode, stdout, stderr)."""
    cmd = [_OPENCLI_CMD, site, command, "--format", "json", "--limit", str(limit)]
    env = dict(_os.environ)
    # Add npm global bin in case it's not already in PATH (Windows)
    npm_bin = str(Path.home() / "AppData" / "Roaming" / "npm")
    if _os.name == "nt" and npm_bin not in env.get("PATH", ""):
        env["PATH"] = npm_bin + ";" + env.get("PATH", "")
    proc = subprocess.run(cmd, capture_output=True, timeout=90, env=env)
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, stdout, stderr


def _fetch_github_trending_sync(limit: int) -> list[TopicItem]:
    """Scrape GitHub Trending page."""
    r = httpx.get(
        "https://github.com/trending",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
        follow_redirects=True,
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    articles = soup.select("article.Box-row")

    topics = []
    for i, article in enumerate(articles[:limit]):
        h2 = article.select_one("h2 a")
        if not h2:
            continue
        href = h2.get("href", "").strip()
        repo = href.lstrip("/")
        url = f"https://github.com{href}"

        p = article.select_one("p")
        desc = p.text.strip() if p else ""

        lang_span = article.select_one("span[itemprop='programmingLanguage']")
        lang = lang_span.text.strip() if lang_span else ""

        # Stars today
        stars_today_el = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = stars_today_el.text.strip() if stars_today_el else ""

        # Total stars and forks
        muted_links = article.select("a.Link--muted")
        total_stars = muted_links[0].text.strip() if muted_links else ""
        forks = muted_links[1].text.strip() if len(muted_links) > 1 else ""

        extra = {}
        if desc:
            extra["description"] = desc
        if lang:
            extra["language"] = lang
        if total_stars:
            extra["stars"] = total_stars
        if forks:
            extra["forks"] = forks

        topics.append(TopicItem(
            title=repo,
            url=url,
            rank=i + 1,
            hot_value=stars_today,
            extra=extra,
        ))

    return topics


async def _fetch_weibo_hot_via_playwright(limit: int = 30) -> list[TopicItem]:
    """Fallback: fetch Weibo hot search via Playwright (m.weibo.cn API)."""
    from playwright.async_api import async_playwright
    from crawlers.base import _run_crawler_in_thread

    async def _do_fetch():
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto("https://m.weibo.cn/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # Call hot search API from page context (has cookies)
            result = await page.evaluate('''async () => {
                try {
                    const resp = await fetch("https://m.weibo.cn/api/container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot");
                    return await resp.json();
                } catch(e) {
                    return { error: e.message };
                }
            }''')

            if result.get("error"):
                raise RuntimeError(f"Weibo API error: {result['error']}")
            if result.get("ok") != 1:
                raise RuntimeError(f"Weibo API returned ok={result.get('ok')}")

            cards = result.get("data", {}).get("cards", [])
            topics = []
            seen = set()
            for card in cards:
                card_group = card.get("card_group", [])
                for item in card_group:
                    title = item.get("desc", "")
                    if not title:
                        continue  # skip section headers / ads
                    if title in seen:
                        continue  # dedup
                    seen.add(title)
                    url = item.get("scheme", "")
                    hot_raw = item.get("desc_extr", "")
                    hot_value = str(hot_raw) if hot_raw else ""
                    topics.append(TopicItem(
                        title=title,
                        url=url,
                        rank=len(topics) + 1,
                        hot_value=hot_value,
                    ))
                    if len(topics) >= limit:
                        break
                if len(topics) >= limit:
                    break
            return topics
        finally:
            await browser.close()
            await pw.stop()

    return await _run_crawler_in_thread(_do_fetch())


async def _fetch_twitter_trending_via_playwright(limit: int = 30) -> list[TopicItem]:
    """Fallback: fetch X/Twitter Trending via Playwright.

    Visits x.com/explore/tabs/trending with the same persistent profile used by
    crawlers/x_search_playwright.py, so an existing X login session is reused.
    The trending list is also visible while logged out.
    """
    from playwright.async_api import async_playwright
    from crawlers.base import _run_crawler_in_thread

    async def _do_fetch():
        # Same profile dir convention as crawlers/x_search_playwright.py,
        # with a CWD-independent fallback.
        user_data_dir = Path("backend/data/x_profile")
        if not user_data_dir.exists():
            user_data_dir = Path("data/x_profile")
        user_data_dir.mkdir(parents=True, exist_ok=True)

        pw = await async_playwright().start()
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
            args=["--no-sandbox"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        try:
            page = await context.new_page()
            await page.goto(
                "https://x.com/explore/tabs/trending",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            # Dismiss the login sheet if it appears (logged-out users)
            try:
                close_btn = page.locator('[data-testid="sheetDialog"] button[aria-label="Close"]')
                if await close_btn.count():
                    await close_btn.first.click()
            except Exception:
                pass

            # Wait for trend items to render
            try:
                await page.wait_for_selector('[data-testid="trend"]', timeout=20000)
            except Exception:
                # Trends did not render — likely a login wall (X requires login
                # to view trends since 2023). Detect after the page settled and
                # report clearly instead of a generic empty result.
                cookies = await context.cookies("https://x.com")
                has_auth = any(c["name"] == "auth_token" for c in cookies)
                body_text = await page.evaluate(
                    "() => document.body ? document.body.innerText.slice(0, 400) : ''"
                )
                if not has_auth and ("See what's happening" in body_text or "Continue with" in body_text):
                    raise RuntimeError(
                        "X 热门榜单需要登录。请先打开 x.com 登录一次"
                        "(登录态将保存到 backend/data/x_profile),之后重新抓取。"
                    )
                await page.wait_for_timeout(3000)

            # Scroll to trigger lazy rendering of more trends
            for _ in range(4):
                await page.mouse.wheel(0, 1200)
                await page.wait_for_timeout(800)

            trends = await page.evaluate("""() => {
                const items = document.querySelectorAll('[data-testid="trend"]');
                const out = [];
                for (const el of items) {
                    const lines = [];
                    for (const span of el.querySelectorAll('span')) {
                        const t = span.textContent.trim();
                        if (t && !lines.includes(t)) lines.push(t);
                    }
                    const link = el.querySelector('a[href*="/search?q="]');
                    const title = lines.find(l => !/posts|trending|trend/i.test(l)) || lines[1] || lines[0] || '';
                    if (!title) continue;
                    const category = lines[0] && lines[0] !== title ? lines[0] : '';
                    const hot = lines.find(l => /posts/i.test(l)) || '';
                    out.push({
                        title: title,
                        url: link ? 'https://x.com' + link.getAttribute('href') : '',
                        category: category,
                        hot_value: hot,
                    });
                }
                return out;
            }""")

            topics = []
            seen = set()
            for t in trends:
                title = str(t.get("title", "")).strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                extra = {}
                if t.get("category"):
                    extra["category"] = t["category"]
                topics.append(TopicItem(
                    title=title,
                    url=str(t.get("url", "")),
                    rank=len(topics) + 1,
                    hot_value=str(t.get("hot_value", "")),
                    extra=extra,
                ))
                if len(topics) >= limit:
                    break

            if not topics:
                raise RuntimeError("X Trending 页面未提取到话题(可能被登录墙拦截)")
            return topics
        finally:
            await context.close()
            await pw.stop()

    return await _run_crawler_in_thread(_do_fetch())


async def fetch_hot_topics(platform: str, limit: int = 30) -> list[TopicItem]:
    """Fetch hot topics for a single platform."""
    if platform not in PLATFORM_CMD:
        raise ValueError(f"Unsupported platform: {platform}")

    # GitHub uses custom scraper instead of autocli
    if platform == "github":
        logger.info(f"[GitHub] Fetching trending repos (limit={limit})")
        try:
            loop = asyncio.get_running_loop()
            topics = await loop.run_in_executor(
                None, partial(_fetch_github_trending_sync, limit)
            )
            logger.info(f"[GitHub] got {len(topics)} repos")
            return topics
        except Exception as e:
            logger.error(f"[GitHub] fetch failed: {type(e).__name__}: {e}")
            raise RuntimeError(f"GitHub Trending 抓取失败: {type(e).__name__}")

    site, command = PLATFORM_CMD[platform]
    logger.info(f"[AutoCLI] Fetching {platform}: autocli {site} {command} --limit {limit}")

    try:
        # Use sync subprocess in thread executor to avoid Windows asyncio NotImplementedError
        loop = asyncio.get_running_loop()
        rc, stdout_text, stderr_text = await loop.run_in_executor(
            None, partial(_run_autocli_sync, site, command, limit)
        )

        if rc != 0:
            # For browser-mode platforms, try Playwright fallback
            if PLATFORM_MODES.get(platform) == "browser":
                logger.warning(f"[AutoCLI] {platform} failed, trying Playwright fallback...")
                try:
                    if platform == "weibo":
                        topics = await _fetch_weibo_hot_via_playwright(limit)
                        logger.info(f"[Playwright] {platform}: got {len(topics)} topics via fallback")
                        return topics
                    if platform == "twitter":
                        topics = await _fetch_twitter_trending_via_playwright(limit)
                        logger.info(f"[Playwright] {platform}: got {len(topics)} topics via fallback")
                        return topics
                except Exception as pw_err:
                    logger.error(f"[Playwright] {platform} fallback also failed: {pw_err}")

            logger.error(f"[AutoCLI] {platform} failed (rc={rc}), stderr: {stderr_text[:300]}")
            raise RuntimeError(stderr_text.strip() or f"autocli exited with code {rc}")

        stdout_text = stdout_text.strip()
        if not stdout_text:
            logger.error(f"[AutoCLI] {platform} empty output, stderr: {stderr_text[:300]}")
            raise RuntimeError("autocli 返回空数据")

        raw = json.loads(stdout_text)
        if not isinstance(raw, list):
            raise ValueError(f"Unexpected output type: {type(raw)}")

        topics = _normalize_topics(platform, raw)
        logger.info(f"[AutoCLI] {platform}: got {len(topics)} topics")
        return topics

    except subprocess.TimeoutExpired:
        logger.error(f"[AutoCLI] {platform} timed out")
        raise RuntimeError("autocli 执行超时")
    except json.JSONDecodeError as e:
        logger.error(f"[AutoCLI] {platform} JSON parse error: {e}")
        raise RuntimeError(f"autocli 返回无效 JSON")
    except FileNotFoundError:
        # AutoCLI not installed — try Playwright fallback for browser-mode platforms
        if PLATFORM_MODES.get(platform) == "browser":
            logger.warning(f"[AutoCLI] autocli not found, trying Playwright fallback for {platform}...")
            try:
                if platform == "weibo":
                    topics = await _fetch_weibo_hot_via_playwright(limit)
                    logger.info(f"[Playwright] {platform}: got {len(topics)} topics via fallback")
                    return topics
                if platform == "twitter":
                    topics = await _fetch_twitter_trending_via_playwright(limit)
                    logger.info(f"[Playwright] {platform}: got {len(topics)} topics via fallback")
                    return topics
            except Exception as pw_err:
                logger.error(f"[Playwright] {platform} fallback also failed: {pw_err}")
        logger.error(f"[AutoCLI] autocli not found in PATH")
        raise RuntimeError("autocli 命令未找到，请确认已安装")
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"[AutoCLI] {platform} unexpected: {type(e).__name__}: {e}")
        raise RuntimeError(f"autocli 执行异常: {type(e).__name__}")


async def fetch_multiple(platforms: list[str], limit: int = 30) -> dict[str, list[TopicItem] | str]:
    """Fetch hot topics for multiple platforms.
    Browser-mode platforms run sequentially (they share browser context),
    public-mode platforms run concurrently.
    Returns {platform: [TopicItem, ...]} or {platform: "error message"}.
    """
    async def _fetch_one(p: str):
        try:
            return p, await fetch_hot_topics(p, limit)
        except Exception as e:
            logger.warning(f"[AutoCLI] {p} failed: type={type(e).__name__}, msg={repr(e)}, str={str(e)}")
            return p, str(e) or type(e).__name__

    browser_platforms = [p for p in platforms if PLATFORM_MODES.get(p) == "browser"]
    public_platforms = [p for p in platforms if PLATFORM_MODES.get(p) != "browser"]

    results: dict[str, list[TopicItem] | str] = {}

    # Browser platforms: run sequentially to avoid conflicts
    for p in browser_platforms:
        platform, result = await _fetch_one(p)
        results[platform] = result

    # Public platforms: run concurrently
    if public_platforms:
        public_results = await asyncio.gather(*[_fetch_one(p) for p in public_platforms])
        for p, result in public_results:
            results[p] = result

    return results
