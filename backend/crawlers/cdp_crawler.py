# intel-monitor/backend/crawlers/cdp_crawler.py
"""
CDP Proxy 爬虫 - 直接调用 web-access skill 的 CDP Proxy API
连接用户已登录的 Chrome 浏览器，无需启动 Claude Code
"""
import json
import asyncio
import httpx
from crawlers.base import CrawlResult, PostData, CommentData
from crawlers.router import CrawlerEntry

CDP_PROXY_URL = "http://localhost:3456"


async def _check_cdp_proxy() -> bool:
    """检查 CDP Proxy 是否运行"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{CDP_PROXY_URL}/targets")
            return resp.status_code == 200
    except Exception:
        return False


async def _cdp_new_tab(url: str) -> str:
    """创建新标签页，返回 target ID"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{CDP_PROXY_URL}/new", params={"url": url})
        data = resp.json()
        return data.get("targetId", "")


async def _cdp_eval(target_id: str, expression: str) -> str:
    """执行 JavaScript 并返回结果"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{CDP_PROXY_URL}/eval",
            params={"target": target_id},
            content=expression,
        )
        try:
            data = resp.json()
            if "error" in data:
                return ""
            return str(data.get("value", ""))
        except Exception:
            return resp.text


async def _cdp_scroll(target_id: str, y: int = 3000):
    """滚动页面"""
    async with httpx.AsyncClient(timeout=10) as client:
        await client.get(f"{CDP_PROXY_URL}/scroll", params={"target": target_id, "y": y})


async def _cdp_close(target_id: str):
    """关闭标签页"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(f"{CDP_PROXY_URL}/close", params={"target": target_id})
    except Exception:
        pass


async def _cdp_wait(target_id: str, seconds: int = 3):
    """等待页面加载"""
    await asyncio.sleep(seconds)


# ===== X (Twitter) 爬虫 =====

X_EXTRACT_POSTS_JS = """
(() => {
    function sanitize(html) {
        // Remove script/iframe/style tags
        html = html.replace(/<(script|iframe|style|object|embed)\\b[^>]*>[\\s\\S]*?<\\/\\1>/gi, '');
        // Strip event handlers
        html = html.replace(/\\s+on\\w+\\s*=\\s*(?:"[^"]*"|'[^']*'|[^\\s>]+)/gi, '');
        return html;
    }
    const tweets = document.querySelectorAll('article[data-testid="tweet"]');
    const results = [];
    for (let i = 0; i < Math.min(tweets.length, 10); i++) {
        const tweet = tweets[i];
        // 内容 - use innerHTML to preserve emoji img tags
        const textEl = tweet.querySelector('[data-testid="tweetText"]');
        const content = textEl ? sanitize(textEl.innerHTML) : '';
        // 链接
        const linkEl = tweet.querySelector('a[href*="/status/"]');
        const href = linkEl ? linkEl.getAttribute('href') : '';
        const url = href ? 'https://x.com' + href : '';
        // 点赞
        const likeEl = tweet.querySelector('[data-testid="like"] span');
        const likesText = likeEl ? likeEl.innerText : '0';
        let likes = 0;
        if (likesText.includes('K')) likes = Math.round(parseFloat(likesText) * 1000);
        else if (likesText.includes('M')) likes = Math.round(parseFloat(likesText) * 1000000);
        else likes = parseInt(likesText) || 0;
        if (content) {
            results.push({ content, url, likes, comments: [] });
        }
    }
    return JSON.stringify({ posts: results, error: '' });
})()
"""

X_EXTRACT_COMMENTS_JS = """
(() => {
    const tweets = document.querySelectorAll('article[data-testid="tweet"]');
    const results = [];
    for (let i = 1; i < Math.min(tweets.length, 21); i++) {
        const tweet = tweets[i];
        const textEl = tweet.querySelector('[data-testid="tweetText"]');
        const text = textEl ? textEl.innerText : '';
        const authorEl = tweet.querySelector('[data-testid="User-Name"] span');
        const author = authorEl ? authorEl.innerText : 'Unknown';
        const likeEl = tweet.querySelector('[data-testid="like"] span');
        const likesText = likeEl ? likeEl.innerText : '0';
        let likes = 0;
        if (likesText.includes('K')) likes = Math.round(parseFloat(likesText) * 1000);
        else if (likesText.includes('M')) likes = Math.round(parseFloat(likesText) * 1000000);
        else likes = parseInt(likesText) || 0;
        if (text) {
            results.push({ text, author, likes });
        }
    }
    results.sort((a, b) => b.likes - a.likes);
    return JSON.stringify(results.slice(0, 10));
})()
"""


async def crawl_x_with_cdp(account_url: str) -> CrawlResult:
    """使用 CDP Proxy 爬取 X (Twitter)"""
    # 检查 CDP Proxy
    if not await _check_cdp_proxy():
        return CrawlResult(
            success=False,
            error_message="CDP Proxy 未运行，请先在 Chrome 中开启远程调试（chrome://inspect/#remote-debugging）"
        )

    target_id = None
    try:
        # 创建新标签页
        target_id = await _cdp_new_tab(account_url)
        if not target_id:
            return CrawlResult(success=False, error_message="无法创建浏览器标签页")

        # 等待页面加载
        await _cdp_wait(target_id, 5)

        # 检查是否需要登录
        page_content = await _cdp_eval(target_id, "document.body.innerText")
        if "Log in" in page_content and "Sign up" in page_content:
            await _cdp_close(target_id)
            return CrawlResult(
                success=False,
                error_message="X (Twitter) 需要登录，请先在 Chrome 中登录 X"
            )

        # 滚动加载更多内容
        for _ in range(3):
            await _cdp_scroll(target_id, 800)
            await _cdp_wait(target_id, 2)

        # 提取帖子
        result_str = await _cdp_eval(target_id, X_EXTRACT_POSTS_JS)
        try:
            # 清理可能的非 JSON 前缀
            start = result_str.find("{")
            end = result_str.rfind("}") + 1
            if start >= 0 and end > start:
                result_str = result_str[start:end]
            data = json.loads(result_str)
        except json.JSONDecodeError:
            return CrawlResult(success=False, error_message="提取帖子失败")

        error = data.get("error", "")
        if error:
            return CrawlResult(success=False, error_message=error)

        posts = []
        all_comments = []
        for item in data.get("posts", []):
            # 获取每条帖子的评论
            post_url = item.get("url", "")
            comments = []
            if post_url:
                try:
                    # 在新标签页打开帖子
                    comment_target = await _cdp_new_tab(post_url)
                    if comment_target:
                        await _cdp_wait(comment_target, 4)
                        # 滚动加载评论
                        await _cdp_scroll(comment_target, 2000)
                        await _cdp_wait(comment_target, 2)
                        # 提取评论
                        comments_str = await _cdp_eval(comment_target, X_EXTRACT_COMMENTS_JS)
                        try:
                            start = comments_str.find("[")
                            end = comments_str.rfind("]") + 1
                            if start >= 0 and end > start:
                                comments_data = json.loads(comments_str[start:end])
                                comments = [
                                    CommentData(
                                        text=c.get("text", ""),
                                        author=c.get("author", ""),
                                        likes=c.get("likes", 0),
                                    )
                                    for c in comments_data
                                ]
                        except json.JSONDecodeError:
                            pass
                        await _cdp_close(comment_target)
                except Exception:
                    pass

            all_comments.extend(comments)
            posts.append(PostData(
                url=post_url,
                content=item.get("content", ""),
                likes=item.get("likes", 0),
                comments=comments,
            ))

        return CrawlResult(posts=posts, success=True)

    except Exception as e:
        return CrawlResult(success=False, error_message=f"CDP 爬取失败: {str(e)}")
    finally:
        if target_id:
            await _cdp_close(target_id)


# ===== 通用网站爬虫 =====

WEBSITE_EXTRACT_JS = """
(() => {{
    const selector = '{selector}';
    const elements = selector ? document.querySelectorAll(selector) : [document.body];
    let content = '';
    for (const el of elements) {{
        content += el.innerText + '\\n';
    }}
    return content.substring(0, 5000);
}})()
"""


async def crawl_website_with_cdp(url: str, css_selector: str = "") -> CrawlResult:
    """使用 CDP Proxy 爬取网站"""
    if not await _check_cdp_proxy():
        return CrawlResult(
            success=False,
            error_message="CDP Proxy 未运行，请先在 Chrome 中开启远程调试"
        )

    target_id = None
    try:
        target_id = await _cdp_new_tab(url)
        if not target_id:
            return CrawlResult(success=False, error_message="无法创建浏览器标签页")

        await _cdp_wait(target_id, 3)

        # 提取内容
        js = WEBSITE_EXTRACT_JS.format(selector=css_selector.replace("'", "\\'"))
        content = await _cdp_eval(target_id, js)

        if not content or not content.strip():
            return CrawlResult(success=False, error_message="未提取到内容")

        posts = [PostData(url=url, content=content.strip())]
        return CrawlResult(posts=posts, success=True)

    except Exception as e:
        return CrawlResult(success=False, error_message=f"CDP 爬取失败: {str(e)}")
    finally:
        if target_id:
            await _cdp_close(target_id)


def build_cdp_entry() -> CrawlerEntry:
    async def _check():
        return await _check_cdp_proxy()

    async def _crawl(platform, account_name, account_url, post_limit=10):
        if platform == "x":
            return await crawl_x_with_cdp(account_url)
        return CrawlResult(success=False, error_message=f"CDP: unsupported platform {platform}")

    return CrawlerEntry(
        name="cdp",
        platforms=frozenset({"x"}),
        crawl=_crawl,
        available=_check,
    )
