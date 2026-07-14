"""
Toutiao crawler via Scrapling StealthyFetcher + targeted DOM extraction.
Replaces the current Playwright CDP approach — no Chrome on 9222 needed.

DOM structure discovered 2026-06-20:
  Search page (so.toutiao.com):  div.result-content > clicks by kind
  Feed/homepage (www.toutiao.com): articles share one big container,
    with <a class="title"> and source text nodes interleaved in DOM order.
    Strategy B uses TreeWalker DOM-order pairing to match each title to its
    subsequent source line ("作者 N评论 X小时前").
"""
import logging
import asyncio
import re
from crawlers.base import CrawlResult, PostData, parse_relative_time, parse_absolute_time

logger = logging.getLogger(__name__)

# ── Result item schemas — what we extract from each div.result-content ──


class ToutiaoScraplingCrawler:
    """Toutiao crawler via Scrapling stealth browser."""

    async def crawl(self, account_url: str) -> CrawlResult:
        """Fetch posts from a Toutiao user/author page."""
        return await asyncio.to_thread(self._do_fetch, account_url)

    async def search_by_keyword(self, keyword: str, limit: int = 20) -> CrawlResult:
        """Search Toutiao via so.toutiao.com."""
        from urllib.parse import quote
        search_url = f"https://so.toutiao.com/search?keyword={quote(keyword)}"
        return await asyncio.to_thread(self._do_fetch, search_url, limit)

    # ── Internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_blocked(text: str) -> bool:
        signals = ["验证码", "captcha", "滑块验证", "异常流量", "安全验证", "请先登录"]
        return any(s in text[:1000].lower() for s in signals)

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").strip()
        if not text:
            return 0
        if "万" in text:
            return int(float(text.replace("万", "")) * 10000)
        try:
            return int(text)
        except ValueError:
            return 0

    @staticmethod
    def _extract_time_from_source(source_text: str):
        """Extract relative time from '来源 · 3天前' or '作者名25分钟前'."""
        if not source_text:
            return None
        # Pattern: "来源 · 3天前" (with dot separator)
        parts = re.split(r'[·\s]+', source_text)
        for part in reversed(parts):
            part = part.strip()
            if not part:
                continue
            t = parse_relative_time(part) or parse_absolute_time(part)
            if t:
                return t
        # Pattern: "作者名25分钟前" (no separator — regex extract)
        m = re.search(r'(\d+\s*个?\s*(?:分钟|小时|天|周|月|年)前)', source_text)
        if m:
            t = parse_relative_time(m.group(1))
            if t:
                return t
        return None

    @staticmethod
    def _extract_author_from_source(source_text: str, published_at) -> str:
        """Extract author name from source line like '大皖新闻25分钟前'."""
        if not source_text or not published_at:
            return ""
        # Remove the time part: find and strip the relative/absolute time
        cleaned = source_text.strip()
        # Strip trailing "·" after removing time
        cleaned = re.sub(r'\s*·\s*$', '', cleaned)
        # Try to extract name before time marker
        m = re.match(r'^(.+?)(\d+\s*个?\s*(?:分钟|小时|天|周|月|年)前)', cleaned)
        m2 = re.match(r'^(.+?)(\d{4}[-/]\d{1,2}[-/]\d{1,2})', cleaned)
        if m:
            return m.group(1).strip()
        if m2:
            return m2.group(1).strip()
        return cleaned

    def _extract_results_via_js(self, page) -> list[dict]:
        """Inject JS to extract structured results from Toutiao pages.

        Handles two page types:
          - Search (so.toutiao.com): div.result-content containers
          - User/homepage (www.toutiao.com): div.ttp-feed-module → a.title
        """
        js = """() => {
            const results = [];

            // Strategy A: Search page — div.result-content
            var searchBlocks = document.querySelectorAll('div.result-content');
            if (searchBlocks.length > 0) {
                for (var si = 0; si < searchBlocks.length; si++) {
                    var c = searchBlocks[si];
                    var fullText = (c.innerText || '').trim();
                    if (fullText.length < 20) continue;

                    // Skip noise blocks
                    var skipPrefixes = ['相关搜索', '大家都在搜', '词语解析'];
                    var shouldSkip = false;
                    for (var sp = 0; sp < skipPrefixes.length; sp++) {
                        if (fullText.indexOf(skipPrefixes[sp]) === 0) {
                            var cl = c.querySelectorAll('a:not([href*="pd=synthesis"])');
                            if (cl.length === 0) { shouldSkip = true; break; }
                        }
                    }
                    if (shouldSkip) continue;

                    var links = c.querySelectorAll('a[href]');
                    var items = [];
                    for (var ai = 0; ai < links.length; ai++) {
                        var a = links[ai];
                        var at = (a.innerText || '').trim();
                        var ah = a.href || '';
                        var ac = (a.className || '');
                        if (!at || at.length < 4 || ah.indexOf('javascript:') === 0) continue;

                        var kind = 'other';
                        if (ac.indexOf('l-card-ti') >= 0 || ac.indexOf('line-clamp-2') >= 0 || ac.indexOf('color-darker') >= 0) {
                            kind = 'title';
                        } else if (ac.indexOf('l-source') >= 0 || ac.indexOf('source') >= 0) {
                            kind = 'source';
                        } else if (ac.indexOf('line-clamp-3') >= 0 && at.length > 30) {
                            kind = 'description';
                        } else if (ac.indexOf('l-container') >= 0 || ac.indexOf('flex-nowrap') >= 0) {
                            kind = 'video-card';
                        }
                        items.push({text: at, href: ah, kind: kind});
                    }

                    // source line from fullText
                    var lines = fullText.split('\\n');
                    var sourceText = '';
                    for (var li = 0; li < lines.length; li++) {
                        var line = lines[li].trim();
                        if (line.indexOf('·') >= 0 && (line.indexOf('天前') >= 0 || line.indexOf('小时前') >= 0 || line.indexOf('分钟前') >= 0)) {
                            sourceText = line; break;
                        }
                    }
                    if (!sourceText) {
                        for (var lj = lines.length - 1; lj >= 0; lj--) {
                            var l = lines[lj].trim();
                            if (l && (l.indexOf('天前') >= 0 || l.indexOf('小时前') >= 0 || l.indexOf('分钟前') >= 0 ||
                                      (l.indexOf('年') >= 0 && l.indexOf('月') >= 0 && l.indexOf('日') >= 0))) {
                                sourceText = l; break;
                            }
                        }
                    }

                    if (items.length > 0) {
                        results.push({fullText: fullText.substring(0, 600), items: items, sourceText: sourceText});
                    }
                }
                return JSON.stringify(results.slice(0, 20));
            }

            // Strategy C: User profile page — content inside div.profile-content or
            // a dedicated feed.  Posts are nested inside feed-item containers.
            // Look for time markers like "3天前", "N播放", "06月09日" in the body.
            var bodyText = document.body ? (document.body.innerText || '').trim() : '';
            // Detect user-page body by profile metadata markers
            var isProfilePage = (bodyText.indexOf('获赞') >= 0 && bodyText.indexOf('粉丝') >= 0);
            var profileFeed = document.querySelector('div.profile-content, div[class*="feed"], div[class*="tab-content"]');
            if (!profileFeed) {
                // Fallback: find div whose innerText contains the posts section
                var divs = document.querySelectorAll('div');
                for (var di = 0; di < divs.length; di++) {
                    var d = divs[di];
                    var dt = (d.innerText || '').trim();
                    // Profile pages have post items with time markers
                    if (dt.length > 300 && dt.length < 20000) {
                        var timeHits = 0;
                        var lines = dt.split('\\n');
                        for (var li = 0; li < lines.length; li++) {
                            var l = lines[li].trim();
                            if (l.indexOf('天前') >= 0 || l.indexOf('小时前') >= 0 || l.indexOf('分钟前') >= 0) timeHits++;
                            if (l && /^\d{2}月\d{2}日$/.test(l)) timeHits++;
                        }
                        if (timeHits >= 3) { profileFeed = d; break; }
                    }
                }
            }
            if (!profileFeed) return '[]';

            // Extract post items — each post is a text block with optional title and time.
            // On profile pages, posts may not be links; content is in innerText lines.
            // Strategy: split by time-marker lines, each section = one post.
            var feedText = (profileFeed.innerText || '').trim();
            var feedLines = feedText.split('\\n');
            var currentPost = { title: '', time: '', views: 0, url: '' };
            var seen = {};

            // Also collect article/video links with their text as anchor points
            var linkMap = {};
            var allLinks = profileFeed.querySelectorAll('a[href*="/article/"], a[href*="/video/"], a[href*="/group/"]');
            for (var ai = 0; ai < allLinks.length; ai++) {
                var a = allLinks[ai];
                var at = (a.innerText || '').trim();
                var ah = a.href || '';
                if (at.length > 3 && ah && !linkMap[ah]) {
                    linkMap[ah] = at;
                }
            }

            // Walk lines, emit post when we hit a time marker.
            // Profile-post layout:
            //   [optional video title]  ← content line
            //   N播放  ← views
            //   作者名3天前  ← author+time on ONE line
            //   ...
            // Capture author+time from combined lines like "爬牙艺术漆3天前"
            for (var li = 0; li < feedLines.length; li++) {
                var line = feedLines[li].trim();
                if (!line) continue;

                // Combined author+time: "爬牙艺术漆3天前", "爬牙艺术漆8天前"
                var authorTimeMatch = line.match(/^(.+?)(\d+天前|\d+小时前|\d+分钟前)$/);
                var isDateLine = /^\d{2}月\d{2}日$/.test(line);
                var isTimeLine = authorTimeMatch || (line.indexOf('天前') >= 0 || line.indexOf('小时前') >= 0 || line.indexOf('分钟前') >= 0);
                var isViewsLine = /^\d+播放$/.test(line) || /^\d+次播放$/.test(line);
                var isCommentLine = /^\d+评论$/.test(line) || /^\d+赞$/.test(line);
                // Filter out noise lines
            var isProfileLine = (line.indexOf('获赞') >= 0 || line.indexOf('粉丝') >= 0 || line.indexOf('关注') >= 0 ||
                line === '全部' || line === '视频' || line === '微头条' || line === '小视频' ||
                line.indexOf('简介') === 0 || line.indexOf('更多信息') === 0 || line.indexOf('转发到头条') === 0 ||
                line.indexOf('分享') === 0 || line.indexOf('评论') === 0 || line === '赞' || line === '关注' ||
                line.indexOf('加载失败') === 0 || line.indexOf('首页') === 0 || line.indexOf('反馈') === 0 ||
                line.indexOf('下载') === 0 || line.indexOf('顶部') === 0 || line.indexOf('登录') === 0 ||
                line === '搜索' || line === '消息' || line === '发布' ||
                /^\d{1,2}:\d{2}$/.test(line));

                if (isTimeLine || isDateLine) {
                    // Flush previous post
                    if (currentPost.title || currentPost.time) {
                        results.push({
                            fullText: '',
                            items: [{text: currentPost.title || currentPost.time, href: currentPost.url, kind: 'title'}],
                            sourceText: currentPost.time
                        });
                    }
                    // Extract author if combined with time
                    var author = '';
                    var timeLine = line;
                    if (authorTimeMatch) {
                        author = authorTimeMatch[1];
                        timeLine = authorTimeMatch[2];
                    }
                    currentPost = { title: '', time: timeLine, views: 0, url: '', author: author };
                } else if (isViewsLine && !currentPost.views) {
                    currentPost.views = parseInt(line) || 0;
                } else if (!isCommentLine && !isProfileLine && line.length > 3 && line.length < 200 && !currentPost.title) {
                    currentPost.title = line;
                }
            }
            // Flush last post
            if (currentPost.title || currentPost.time) {
                results.push({
                    fullText: '',
                    items: [{text: currentPost.title || currentPost.time, href: currentPost.url, kind: 'title'}],
                    sourceText: currentPost.time
                });
            }

            // Fill in URLs from linkMap by substring matching.
            // Also set fullText for the card content.
            var linkEntries = [];
            for (var k in linkMap) { linkEntries.push({url: k, text: linkMap[k]}); }
            for (var ri = 0; ri < results.length; ri++) {
                var r = results[ri];
                if (r.items && r.items[0]) {
                    var title = r.items[0].text || '';
                    if (!r.items[0].href) {
                        for (var ei = 0; ei < linkEntries.length; ei++) {
                            if (title.indexOf(linkEntries[ei].text) >= 0 || linkEntries[ei].text.indexOf(title) >= 0) {
                                r.items[0].href = linkEntries[ei].url;
                                break;
                            }
                        }
                    }
                    // Attach author from parsed source (e.g. "爬牙艺术漆3天前" → author="爬牙艺术漆")
                    if (r.sourceText && !r.author) {
                        var m = r.sourceText.match(/^(.+?)(\d+天前|\d+小时前|\d+分钟前|\d{2}月\d{2}日)$/);
                        if (m) r.author = m[1];
                    }
                }
            }

            return JSON.stringify(results.slice(0, 20));
        }"""
        raw = page.evaluate(js)
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    def _parse_to_posts(self, result_blocks: list[dict]) -> list[PostData]:
        """Convert JS-extracted blocks into PostData list."""
        posts = []
        SKIP_WORDS = {"词语解析", "大家都在搜"}
        SKIP_REGEX = re.compile(r'^\d{1,2}:\d{2}$')  # video duration "00:15"
        # Time-only titles mean we couldn't find real content for this post
        TIME_ONLY_REGEX = re.compile(r'^\d+天前$|^\d+小时前$|^\d+分钟前$|^\d{2}月\d{2}日$')
        NOISE_WORDS = {"复制链接", "转发到头条", "登录", "搜索", "消息", "发布", "关注", "推荐"}

        for block in result_blocks:
            items = block.get("items", [])
            if not items:
                continue

            title = items[0].get("text", "")[:200]
            url = items[0].get("href", "")

            # Skip sidebar noise / placeholder / time-only
            if any(w in title for w in SKIP_WORDS | NOISE_WORDS):
                continue
            if SKIP_REGEX.match(title.strip()):
                continue
            if TIME_ONLY_REGEX.match(title.strip()):
                continue

            # Source text for author + time
            source_text = block.get("sourceText", "")

            published_at = None
            if source_text:
                published_at = self._extract_time_from_source(source_text)

            # Fallback: extract time from fullText
            if not published_at:
                full = block.get("fullText", "")
                published_at = self._extract_time_from_source(full)

            author_name = ""
            if source_text and published_at:
                author_name = self._extract_author_from_source(source_text, published_at)

            # Views from fullText or sourceText
            views = 0
            m = re.search(r'(\d+\.?\d*万?)\s*次播放', block.get("fullText", ""))
            if not m:
                m = re.search(r'(\d+\.?\d*万?)\s*播放', block.get("fullText", ""))
            if m:
                views = self._parse_count(m.group(1))

            content = block.get("fullText", "")[:500]

            posts.append(PostData(
                url=url,
                title=title,
                content=content,
                author_name=author_name,
                views=views,
                published_at=published_at,
            ))

        return posts

    def _do_fetch(self, url: str, limit: int = 20) -> CrawlResult:
        from scrapling import StealthyFetcher

        # Determine page type: user page needs real_chrome
        is_user_page = '/c/user/' in url or url.rstrip('/').endswith('/c/user')

        # Closure for page_action to write into
        extracted = {}

        def page_action(page):
            import time
            time.sleep(3)
            # Scroll to trigger lazy loading
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1)
            time.sleep(2)
            extracted["blocks"] = self._extract_results_via_js(page)
            extracted["url"] = page.url
            extracted["title"] = page.title()
            extracted["body"] = page.evaluate("() => document.body ? document.body.innerText.substring(0, 2000) : ''")
            return None

        try:
            logger.info(f"ToutiaoScrapling: fetching {url} (real_chrome={is_user_page})")
            StealthyFetcher.fetch(
                url=url,
                headless=True,
                wait=5000,
                solve_cloudflare=True,
                disable_resources=True,
                block_ads=True,
                timeout=90000,
                locale="zh-CN",
                page_action=page_action,
                real_chrome=is_user_page,
            )
        except Exception as e:
            logger.exception("ToutiaoScrapling fetch error")
            return CrawlResult(success=False, error_message=f"Scrapling 抓取失败: {e}")

        body_text = extracted.get("body", "")
        if self._is_blocked(body_text):
            return CrawlResult(success=False, error_message="被今日头条反爬拦截")

        blocks = extracted.get("blocks", [])
        if not blocks:
            return CrawlResult(
                success=False,
                error_message="未找到搜索结果 — 页面结构可能已变化"
            )

        posts = self._parse_to_posts(blocks)
        posts = posts[:limit]

        logger.info(f"ToutiaoScrapling: extracted {len(posts)} posts")
        return CrawlResult(posts=posts, success=len(posts) > 0)
