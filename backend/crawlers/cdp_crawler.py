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
    """创建新标签页，返回 target ID（v2.5.3+ /new 为 POST body=URL）"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{CDP_PROXY_URL}/new", content=url)
        data = resp.json()
        return data.get("targetId", "")


async def _cdp_req_with_retry(method: str, path: str, retries: int = 3) -> bool:
    """带重试的 CDP 代理请求（代理重启后 attach 有短暂失败期，需重试自愈）。"""
    import asyncio as _aio
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                if method == "GET":
                    resp = await client.get(f"{CDP_PROXY_URL}{path}")
                else:
                    resp = await client.post(f"{CDP_PROXY_URL}{path}")
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await _aio.sleep(2 * (attempt + 1))
    return False


async def _cdp_focus(target_id: str) -> bool:
    """激活标签页（后台 tab 收不到输入事件，必须 bringToFront）。"""
    return await _cdp_req_with_retry("GET", f"/focus?target={target_id}")


async def _cdp_key(target_id: str, key: str = "Escape") -> bool:
    """发送键盘事件（关闭弹层/对话框）。"""
    return await _cdp_req_with_retry("GET", f"/key?target={target_id}&key={key}")


async def _cdp_wheel(target_id: str, delta_y: int = 500, times: int = 2) -> bool:
    """发送真实滚轮事件（可信输入，触发 Facebook 等站点的懒加载）。"""
    return await _cdp_req_with_retry("GET", f"/wheel?target={target_id}&deltaY={delta_y}&times={times}")


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


# ===== Facebook 爬虫（真实浏览器模拟人浏览） =====
# 通过 CDP Proxy 驱动用户已登录的 Chrome 直接访问账号主页，用真实滚轮事件
# 触发懒加载（FB 只认可信输入事件），边滚边提取，按帖子链接去重。

FB_EXPAND_POSTS_JS = r"""
(() => {
    // 点击所有"展开/查看更多/See more"按钮，展开折叠的长文
    let clicked = 0;
    for (const a of document.querySelectorAll('div[role="article"]')) {
        for (const b of a.querySelectorAll('div[role="button"], span')) {
            const t = (b.innerText || '').trim();
            if (t === '展开' || t === '查看更多' || t === '查看完整内容' || /^see more$/i.test(t)) {
                try { b.click(); clicked++; } catch (e) {}
            }
        }
    }
    return JSON.stringify({ clicked });
})()
"""

FB_EXTRACT_POSTS_JS = r"""
(() => {
    function num(s) {
        const m = (s || '').match(/[\d,.]+/);
        return m ? parseInt(m[0].replace(/,/g, '')) || 0 : 0;
    }
    const arts = document.querySelectorAll('div[role="article"]');
    const posts = [];
    for (const a of arts) {
        // 帖子链接：优先 /posts/ /videos/ /photos/ /reel/ /permalink.php story_fbid fbid=
        const hrefs = Array.from(a.querySelectorAll('a[href]')).map(x => x.getAttribute('href') || '');
        const pl = hrefs.find(h => /\/(posts|videos|photos|reel)\/|story_fbid|fbid=|permalink\.php/.test(h)) || '';
        let url = '';
        if (pl) {
            // 去 query 参数（comment_id/reply 等变体归一到帖子主体）
            const clean = pl.split('?')[0].split('&')[0];
            url = clean.startsWith('http') ? clean : 'https://www.facebook.com' + clean;
        }
        // 正文：优先显式消息容器，否则取最长的 dir=auto 文本块
        let content = '';
        const msgEl = a.querySelector('div[data-ad-comet-preview="message"], div[data-ad-preview="message"]');
        if (msgEl) {
            content = (msgEl.innerText || '').trim();
        } else {
            let best = '';
            for (const d of a.querySelectorAll('div[dir="auto"]')) {
                const t = (d.innerText || '').trim();
                if (t.length > best.length && t.length > 10) best = t;
            }
            content = best;
        }
        // 去掉折叠标记后缀："… 展开" / "… 查看更多" / "… See more"
        content = content.replace(/…\s*(展开|查看更多|查看完整内容)\s*$/, '')
                         .replace(/…\s*see more\s*$/i, '').trim();
        // 时间：aria-label（通常含完整时间戳）优先，其次时间链接文本
        let timeStr = '';
        const timeLabels = Array.from(a.querySelectorAll('a[aria-label], span[aria-label], div[aria-label]'))
            .map(x => x.getAttribute('aria-label') || '')
            .filter(l => /月|日|年|小时|分钟|昨天|刚刚|hour|min|yesterday|ago|\d+[hdwm]/.test(l));
        if (timeLabels.length) timeStr = timeLabels[0];
        if (!timeStr) {
            const timeLinks = Array.from(a.querySelectorAll('a[href]'))
                .map(x => (x.innerText || '').trim())
                .filter(t => /月|日|年|小时|分钟|昨天|刚刚|hour|min|yesterday|ago|\d+[hdwm]/.test(t));
            if (timeLinks.length) timeStr = timeLinks[0];
        }
        // 互动数据：带 aria-label 的元素按关键词归类
        let likes = 0, comments = 0, shares = 0;
        const labels = Array.from(a.querySelectorAll('span[aria-label], div[aria-label], a[aria-label]'))
            .map(x => x.getAttribute('aria-label') || '');
        for (const l of labels) {
            if (/心情|回应|赞|reaction|like/i.test(l) && !/评论|分享|comment|share/i.test(l)) likes = Math.max(likes, num(l));
            else if (/评论|comment/i.test(l)) comments = Math.max(comments, num(l));
            else if (/分享|转发|share/i.test(l)) shares = Math.max(shares, num(l));
        }
        // 兜底：footer 尾部纯数字行按 [赞, 评论, 分享] 顺序解析
        const innerText = a.innerText || '';
        if (!likes || !comments || !shares) {
            const lines = innerText.split('\n').map(s => s.trim()).filter(s => /^[\d,.]+$/.test(s));
            const tail = lines.slice(-3);
            if (tail.length === 3) {
                if (!likes) likes = num(tail[0]);
                if (!comments) comments = num(tail[1]);
                if (!shares) shares = num(tail[2]);
            }
        }
        // 图片：FB CDN 图
        const imgs = Array.from(a.querySelectorAll('img[src*="scontent"], img[src*="fbcdn"]'))
            .map(i => i.src).filter(Boolean);
        posts.push({
            url, content, timeStr, likes, comments, shares,
            images: imgs.slice(0, 5),
            innerText: innerText.slice(0, 1500),
        });
    }
    return JSON.stringify(posts);
})()
"""

FB_LOGIN_CHECK_JS = "document.cookie.includes('c_user') ? 'yes' : 'no'"


def _parse_fb_time(time_str: str, inner_text: str = "") -> "datetime | None":
    """解析 Facebook 时间文本为 naive UTC datetime（中文界面为主）。

    覆盖：刚刚 / X分钟 / X小时 / 昨天 / X天 / X周 / X月X日 / X年X月X日(时分秒) /
    Yesterday / Xh / Xm / Xd / X weeks ago（后者复用 parse_relative_time）。
    """
    from datetime import datetime, timedelta, timezone
    import re as _re
    from crawlers.base import parse_relative_time

    text = (time_str or inner_text or "").strip()
    if not text:
        return None
    now_cn = datetime.now(timezone(timedelta(hours=8)))

    def to_naive_utc(dt_cn):
        return (dt_cn - timedelta(hours=8)).replace(tzinfo=None)

    if "刚刚" in text or "just now" in text.lower():
        return to_naive_utc(now_cn)
    m = _re.search(r'(\d+)\s*分钟', text)
    if m: return to_naive_utc(now_cn - timedelta(minutes=int(m.group(1))))
    m = _re.search(r'(\d+)\s*小时', text)
    if m: return to_naive_utc(now_cn - timedelta(hours=int(m.group(1))))
    m = _re.search(r'(\d+)\s*天', text)
    if m: return to_naive_utc(now_cn - timedelta(days=int(m.group(1))))
    m = _re.search(r'(\d+)\s*周', text)
    if m: return to_naive_utc(now_cn - timedelta(weeks=int(m.group(1))))
    if "昨天" in text:
        m = _re.search(r'(\d{1,2}):(\d{2})', text)
        y = now_cn - timedelta(days=1)
        if m: y = y.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return to_naive_utc(y)
    # 绝对日期：X年X月X日 [HH:MM[:SS]]
    m = _re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        tm = _re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', text)
        hh, mm, ss = (int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0)) if tm else (0, 0, 0)
        return to_naive_utc(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), hh, mm, ss))
    m = _re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        tm = _re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', text)
        hh, mm, ss = (int(tm.group(1)), int(tm.group(2)), int(tm.group(3) or 0)) if tm else (0, 0, 0)
        year = now_cn.year
        dt = datetime(year, int(m.group(1)), int(m.group(2)), hh, mm, ss, tzinfo=now_cn.tzinfo)
        if dt > now_cn + timedelta(days=1):
            dt = dt.replace(year=year - 1)
        return to_naive_utc(dt)
    # 英文相对时间："Yesterday", "Xh", "Xm", "Xd", "X weeks ago"
    if "yesterday" in text.lower():
        return to_naive_utc(now_cn - timedelta(days=1))
    m = _re.search(r'(\d+)\s*h\b', text, _re.IGNORECASE)
    if m: return to_naive_utc(now_cn - timedelta(hours=int(m.group(1))))
    m = _re.search(r'(\d+)\s*m\b', text, _re.IGNORECASE)
    if m: return to_naive_utc(now_cn - timedelta(minutes=int(m.group(1))))
    m = _re.search(r'(\d+)\s*d\b', text, _re.IGNORECASE)
    if m: return to_naive_utc(now_cn - timedelta(days=int(m.group(1))))
    return parse_relative_time(text)


async def crawl_facebook_with_cdp(account_url: str, post_limit: int = 10) -> CrawlResult:
    """模拟人浏览：激活标签页 → 关闭弹层 → 真实滚轮滚动 → 边滚边提取。"""
    if not await _check_cdp_proxy():
        return CrawlResult(
            success=False,
            error_message="CDP Proxy 未运行，Facebook 模拟人模式不可用（降级 CSE 快照模式）"
        )

    target_id = None
    try:
        target_id = await _cdp_new_tab(account_url)
        if not target_id:
            return CrawlResult(success=False, error_message="无法创建浏览器标签页")

        # 激活标签页：后台 tab 收不到输入事件
        await _cdp_focus(target_id)
        await _cdp_wait(target_id, 6)

        # 关闭可能的弹层/对话框
        await _cdp_key(target_id, "Escape")
        await _cdp_wait(target_id, 2)

        # 登录检查
        login_state = (await _cdp_eval(target_id, FB_LOGIN_CHECK_JS)).strip().strip('"')
        if login_state != "yes":
            return CrawlResult(
                success=False,
                error_message="Chrome 未登录 Facebook，请先在 Chrome 中登录 Facebook 后重试",
            )

        # 边滚边提取，按链接去重。
        # FB 懒加载较慢：每轮滚 3×600px 后等待渲染；
        # 轮数上限随目标条数扩展（每条帖子约需滚动 600-900px），
        # 连续 6 轮（约 30 秒）无新帖才判定到底；滚轮瞬时失败不硬停。
        seen: dict[str, dict] = {}
        no_new_rounds = 0
        max_rounds = max(25, post_limit * 3)
        for _ in range(max_rounds):
            # 展开折叠的长文（"展开 / 查看更多 / See more"）
            try:
                await _cdp_eval(target_id, FB_EXPAND_POSTS_JS)
                await _cdp_wait(target_id, 1)
            except Exception:
                pass

            wheel_ok = await _cdp_wheel(target_id, delta_y=600, times=3)
            await _cdp_wait(target_id, 4)

            if not wheel_ok:
                # 滚轮失败（代理瞬时故障）：计入无新增轮次，继续尝试
                no_new_rounds += 1
            else:
                raw = await _cdp_eval(target_id, FB_EXTRACT_POSTS_JS)
                data: list[dict] = []
                parsed = False
                try:
                    start, end = raw.find("["), raw.rfind("]") + 1
                    if start >= 0 and end > start:
                        data = json.loads(raw[start:end])
                        parsed = True
                except json.JSONDecodeError:
                    pass

                new_count = 0
                if parsed:
                    for item in data:
                        content = (item.get("content") or "").strip()
                        images = item.get("images") or []
                        if not content and not images:
                            continue  # 空内容且无图（评论链接等噪音）跳过
                        key = item.get("url") or content[:60]
                        if key and key not in seen:
                            seen[key] = item
                            new_count += 1

                if new_count == 0:
                    no_new_rounds += 1
                else:
                    no_new_rounds = 0

            # 连续 6 轮（约 30 秒）无新帖加载，或数量达标，停止滚动
            if no_new_rounds >= 6:
                break
            if len(seen) >= max(post_limit * 3, 30):
                break

        if not seen:
            return CrawlResult(
                success=False,
                error_message="未提取到帖子（可能该账号隐私设置限制了公开可见帖子）",
            )

        posts: list[PostData] = []
        for item in list(seen.values())[:post_limit]:
            content = (item.get("content") or "").strip()
            posts.append(PostData(
                url=item.get("url", ""),
                title=content[:80],
                content=content,
                likes=item.get("likes") or 0,
                comments_count=item.get("comments") or 0,
                shares=item.get("shares") or 0,
                images=list(item.get("images") or [])[:5],
                published_at=_parse_fb_time(item.get("timeStr") or "", item.get("innerText") or ""),
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
        if platform == "facebook":
            return await crawl_facebook_with_cdp(account_url, post_limit)
        return CrawlResult(success=False, error_message=f"CDP: unsupported platform {platform}")

    return CrawlerEntry(
        name="cdp",
        platforms=frozenset({"x", "facebook"}),
        crawl=_crawl,
        available=_check,
    )
