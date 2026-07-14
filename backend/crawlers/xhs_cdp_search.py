# intel-monitor/backend/crawlers/xhs_cdp_search.py
"""
Xiaohongshu CDP search — Chrome CDP 浏览器驱动搜索
通过 CDP Proxy (localhost:3456) 操控用户已登录的 Chrome 浏览器，
绕过 XHS 反爬机制，实现关键词搜索 + 笔记详情提取。

与 opencli_crawler 的对比：
- opencli: typeText + pressKey Enter 模拟输入 → 可能静默失败 → 返回推荐流
- CDP:     直接 URL 导航 + CDP 点击进入详情 → 准确的搜索结果 + 完整正文

依赖：CDP Proxy 运行中 (node cdp-proxy.mjs)，Chrome 已登录小红书。
"""

import json
import logging
import asyncio
import subprocess
import os
from urllib.parse import quote

import httpx

from crawlers.base import CrawlResult, PostData, CommentData, parse_relative_time

logger = logging.getLogger(__name__)

CDP_PROXY_URL = "http://localhost:3456"

# CDP Proxy startup tracking
_cdp_proxy_process: subprocess.Popen | None = None

# Path to cdp-proxy.mjs relative to project root
def _cdp_proxy_script() -> str:
    """Resolve cdp-proxy.mjs path (project .claude/skills/web-access/scripts/)."""
    # backend/crawlers/ -> go up 2 levels to project root
    this_dir = os.path.dirname(os.path.abspath(__file__))           # .../backend/crawlers
    project_root = os.path.dirname(os.path.dirname(this_dir))       # .../
    return os.path.join(project_root, ".claude", "skills", "web-access", "scripts", "cdp-proxy.mjs")


async def _ensure_cdp_proxy() -> bool:
    """Ensure CDP Proxy is running; auto-start it if not. Returns True if ready."""
    global _cdp_proxy_process

    # Already running → check health
    if await _check_cdp_proxy():
        return True

    # Check if we have a stale child process
    if _cdp_proxy_process is not None:
        if _cdp_proxy_process.poll() is not None:
            _cdp_proxy_process = None  # child exited

    # Try to start the proxy
    script = _cdp_proxy_script()
    if not os.path.exists(script):
        logger.warning("[XHS CDP] cdp-proxy.mjs not found at %s", script)
        return False

    logger.info("[XHS CDP] Auto-starting CDP Proxy: node %s", script)
    try:
        _cdp_proxy_process = subprocess.Popen(
            ["node", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.warning("[XHS CDP] Node.js not found — cannot auto-start CDP Proxy")
        return False
    except Exception as e:
        logger.warning("[XHS CDP] Failed to start CDP Proxy: %s", e)
        return False

    # Wait up to 5 seconds for the proxy to come online
    for _ in range(10):
        await asyncio.sleep(0.5)
        if await _check_cdp_proxy():
            return True

    logger.warning("[XHS CDP] CDP Proxy started but not ready within 5s")
    return False


# ── CDP Proxy HTTP helpers ──────────────────────────────────────────────

async def _check_cdp_proxy() -> bool:
    """检查 CDP Proxy 是否运行且已连接 Chrome。"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{CDP_PROXY_URL}/health")
            data = resp.json()
            return data.get("connected", False)
    except Exception:
        return False


async def _cdp_new_tab(url: str = "about:blank") -> str:
    """创建新后台标签页，返回 targetId。"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{CDP_PROXY_URL}/new", content=url.encode("utf-8"))
        data = resp.json()
        return data.get("targetId", "")


async def _cdp_navigate(target_id: str, url: str) -> None:
    """导航标签页到 URL（CDP Proxy 自动等待 document.readyState === 'complete'）。
    使用 bytes 传递中文 URL，避免 httpx 默认行为破坏 UTF-8 编码。"""
    async with httpx.AsyncClient(timeout=60) as client:
        await client.post(
            f"{CDP_PROXY_URL}/navigate",
            params={"target": target_id},
            content=url.encode("utf-8"),
        )


async def _cdp_eval(target_id: str, expression: str) -> str:
    """在标签页中执行 JS 并返回字符串结果。"""
    async with httpx.AsyncClient(timeout=15) as client:
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


async def _cdp_close(target_id: str) -> None:
    """关闭标签页。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(
                f"{CDP_PROXY_URL}/close",
                params={"target": target_id},
            )
    except Exception:
        pass


# ── Count parsing ───────────────────────────────────────────────────────

def _parse_count(text: str) -> int:
    """解析 XHS 计数格式：'1.3万', '927', '0'。"""
    text = (text or "").strip()
    if not text:
        return 0
    if "万" in text:
        try:
            return int(float(text.replace("万", "")) * 10000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0


# ── Browser-side JS snippets ────────────────────────────────────────────

# 搜索结果页：提取所有笔记卡片（排除相关搜索 query-note-item）
_EXTRACT_SEARCH_CARDS_JS = r"""
(function(){
  function cleanText(v) { return (v||'').replace(/\s+/g,' ').trim(); }
  var cards = document.querySelectorAll('section.note-item');
  var results = [];
  for (var i=0; i<cards.length; i++) {
    var c = cards[i];
    if (c.classList.contains('query-note-item')) continue;
    var titleEl = c.querySelector('.title');
    var nameEl = c.querySelector('.name');
    var countEl = c.querySelector('.count');
    var linkEl = c.querySelector('a.cover');
    results.push({
      title: cleanText(titleEl ? titleEl.textContent : ''),
      author: cleanText(nameEl ? nameEl.textContent : ''),
      likes: cleanText(countEl ? countEl.textContent : '0'),
      url: linkEl ? linkEl.href : ''
    });
  }
  return JSON.stringify(results);
})()
"""

# 笔记详情页：提取正文、互动数据、标签、图片
_EXTRACT_NOTE_DETAIL_JS = r"""
(function(){
  function cleanText(v) { return (v||'').replace(/\s+/g,' ').trim(); }
  var desc = document.querySelector('#detail-desc');
  var content = desc ? desc.textContent.trim() : '';
  var dateEl = document.querySelector('.bottom-container .date');
  var date = dateEl ? cleanText(dateEl.textContent).replace('编辑于 ','') : '';
  // Interaction counts scoped to the note's engage bar (NOT the comment section)
  var engageBar = document.querySelector('.buttons.engage-bar-style');
  var likeEl = engageBar ? engageBar.querySelector('.like-wrapper .count') : null;
  var collectEl = engageBar ? engageBar.querySelector('.collect-wrapper .count') : null;
  var commentEl = engageBar ? engageBar.querySelector('.chat-wrapper .count') : null;
  // 标签
  var tags = [];
  var tagEls = document.querySelectorAll('#detail-desc a[id^="hash"]');
  for (var i=0; i<tagEls.length; i++) {
    tags.push(cleanText(tagEls[i].textContent));
  }
  // 图片（小红书搜索结果不展示，无需提取）
  var imgs = [];
  return JSON.stringify({
    title: document.title.replace(' - 小红书',''),
    date: date,
    likes: cleanText(likeEl ? likeEl.textContent : '0'),
    collects: cleanText(collectEl ? collectEl.textContent : '0'),
    comments: cleanText(commentEl ? commentEl.textContent : '0'),
    tags: tags,
    content: content.slice(0,5000),
    images: imgs.slice(0,9),
    url: location.href
  });
})()
"""

# 提取热门评论（需已打开笔记详情页，且评论区已滚动加载）
_EXTRACT_HOT_COMMENTS_JS = r"""
(function(){
  function parseCount(el) {
    if (!el) return 0;
    var t = (el.textContent||'').trim();
    if (t === '赞' || t === '回复' || t === '') return 0;
    var n = parseInt(t, 10);
    return isNaN(n) ? 0 : n;
  }
  function cleanText(v) { return (v||'').replace(/\s+/g,' ').trim(); }

  var comments = [];
  var parentComments = document.querySelectorAll('.parent-comment');
  for (var i = 0; i < parentComments.length; i++) {
    var pc = parentComments[i];
    var parentItem = pc.querySelector('.comment-item:not(.comment-item-sub)');
    if (!parentItem) continue;

    var extract = function(el) {
      return {
        author: cleanText((el.querySelector('.author .name')||{}).textContent || ''),
        text: cleanText((el.querySelector('.content .note-text')||{}).textContent || ''),
        date: cleanText((el.querySelector('.date span:first-child')||{}).textContent || ''),
        likes: parseCount(el.querySelector('.like .count')),
        is_author: !!el.querySelector('.author .tag')
      };
    };

    var parent = extract(parentItem);
    var subItems = pc.querySelectorAll('.comment-item-sub');
    var subs = [];
    for (var j = 0; j < subItems.length; j++) {
      subs.push(extract(subItems[j]));
    }
    parent.replies = subs;
    comments.push(parent);
  }
  return JSON.stringify(comments.slice(0, 20));
})()
"""

# 登录检测：XHS 未登录时信息流顶部会出现"登录后推荐"
_DETECT_LOGIN_JS = (
    "document.body?.innerText?.includes('登录后推荐') ? 'login_wall' : 'ok'"
)


# ── Public API ──────────────────────────────────────────────────────────

async def search_xhs(keyword: str, limit: int = 20) -> CrawlResult:
    """通过 CDP 浏览器驱动搜索小红书笔记，返回含正文的 CrawlResult。

    流程：
    1. 检查 CDP Proxy 连通性
    2. 创建标签页 → 导航到搜索结果页
    3. 检测登录墙（未登录则报错）
    4. 提取搜索结果卡片
    5. 对每条笔记：JS 点击进入详情 → 提取正文/互动/标签/图片 → 返回搜索页
    6. 返回完整的 PostData 列表

    Args:
        keyword: 搜索关键词（支持中文）
        limit: 最大结果数（1-50）

    Returns:
        CrawlResult: posts 中包含 title, content, author_name, likes,
        comments_count, bookmarks, images, published_at
    """
    # ── 1. 基础设施检查（自动启动 CDP Proxy 如果未运行）──
    if not await _ensure_cdp_proxy():
        return CrawlResult(
            success=False,
            error_message=(
                "CDP Proxy 未运行或未连接 Chrome。"
                "请先以 --remote-debugging-port=9222 启动 Chrome，"
                "然后运行 node cdp-proxy.mjs"
            ),
        )

    limit = max(1, min(limit, 50))
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword, safe='')}"
    target_id = None

    try:
        # ── 2. 创建标签页并导航到搜索结果 ──
        target_id = await _cdp_new_tab()
        if not target_id:
            return CrawlResult(success=False, error_message="无法创建浏览器标签页")

        await _cdp_navigate(target_id, search_url)
        # XHS 是 React SPA，额外等待水合和懒加载
        await asyncio.sleep(4)

        # ── 3. 登录墙检测 ──
        login_state = await _cdp_eval(target_id, _DETECT_LOGIN_JS)
        if login_state == "login_wall":
            await _cdp_close(target_id)
            return CrawlResult(
                success=False,
                error_message="小红书需要登录。请在 Chrome 中打开 xiaohongshu.com 扫码登录后重试。",
            )

        # ── 4. 提取搜索结果卡片 ──
        cards_json = await _cdp_eval(target_id, _EXTRACT_SEARCH_CARDS_JS)
        try:
            cards = json.loads(cards_json)
        except json.JSONDecodeError:
            await _cdp_close(target_id)
            return CrawlResult(success=False, error_message="搜索结果 DOM 提取失败")

        if not cards:
            await _cdp_close(target_id)
            return CrawlResult(
                success=False,
                error_message=f"关键词 '{keyword}' 未找到搜索结果",
            )

        logger.info("[XHS CDP] 搜索 '%s' → %d 条结果", keyword, len(cards))

        # ── 5. 逐条打开详情、提取内容 ──
        posts: list[PostData] = []
        card_count = min(len(cards), limit)

        for idx in range(card_count):
            card = cards[idx]
            card_title = card.get("title", "")
            card_author = card.get("author", "")
            card_likes = card.get("likes", "0")

            try:
                # JS 点击卡片封面 → XHS SPA 导航到笔记详情
                click_js = (
                    f"(function(){{"
                    f"var cards=document.querySelectorAll('section.note-item');"
                    f"if(cards.length>{idx}){{"
                    f"var a=cards[{idx}].querySelector('a.cover');"
                    f"if(a)a.click();"
                    f"}}"
                    f"return 'clicked';"
                    f"}})()"
                )
                await _cdp_eval(target_id, click_js)
                await asyncio.sleep(3)

                # 提取笔记详情
                detail_json = await _cdp_eval(target_id, _EXTRACT_NOTE_DETAIL_JS)
                try:
                    detail = json.loads(detail_json)
                except json.JSONDecodeError:
                    detail = {}

                # 解析发布时间
                date_str = detail.get("date", "")
                published_at = parse_relative_time(date_str) if date_str else None

                # 提取字段
                title = detail.get("title") or card_title
                content = detail.get("content") or card_title
                likes = _parse_count(detail.get("likes", card_likes))
                comments_count = _parse_count(detail.get("comments", "0"))
                bookmarks = _parse_count(detail.get("collects", "0"))
                images = detail.get("images", [])
                tags = detail.get("tags", [])

                # 把标签追加到正文末尾
                if tags:
                    content = content + "\n\n" + " ".join(tags)

                # ── 提取热门评论（滚动触发加载后抓取）──
                hot_comments: list[dict] = []
                try:
                    # 滚动到评论区触发懒加载
                    await _cdp_eval(target_id,
                        "var el=document.querySelector('.comments-el');"
                        "if(el)el.scrollIntoView({block:'center'});"
                        "'scrolled'")
                    await asyncio.sleep(1.5)
                    # 提取评论
                    comments_json = await _cdp_eval(target_id, _EXTRACT_HOT_COMMENTS_JS)
                    if comments_json:
                        hot_comments = json.loads(comments_json)
                except Exception:
                    pass  # 评论提取失败不影响正文

                posts.append(PostData(
                    url=detail.get("url") or card.get("url", ""),
                    title=title,
                    content=content,
                    likes=likes,
                    comments_count=comments_count,
                    bookmarks=bookmarks,
                    author_name=card_author,
                    published_at=published_at,
                    images=images,
                ))
                # 把评论数据挂到 PostData.comments
                if hot_comments:
                    posts[-1].comments = [
                        CommentData(
                            text=c.get("text", ""),
                            author=c.get("author", ""),
                            likes=c.get("likes", 0),
                            url=posts[-1].url,
                        )
                        for c in hot_comments if c.get("text")
                    ]

            except Exception as e:
                # 单条失败不阻塞整体，用卡片数据 fallback
                logger.warning("[XHS CDP] 第 %d 条笔记详情提取失败: %s", idx + 1, e)
                if card_title:
                    posts.append(PostData(
                        url=card.get("url", ""),
                        title=card_title,
                        content=card_title,
                        likes=_parse_count(card_likes),
                        author_name=card_author,
                    ))

            # 返回搜索页（除了最后一条）
            if idx < card_count - 1:
                try:
                    await _cdp_navigate(target_id, search_url)
                    await asyncio.sleep(3)
                except Exception:
                    break  # 导航失败则终止后续提取

        # ── 6. 清理并返回 ──
        await _cdp_close(target_id)

        return CrawlResult(
            posts=posts,
            success=len(posts) > 0,
            error_message="" if posts else "所有笔记详情提取失败",
        )

    except Exception as e:
        logger.exception("[XHS CDP] 搜索异常: %s", e)
        if target_id:
            await _cdp_close(target_id)
        return CrawlResult(success=False, error_message=str(e))
