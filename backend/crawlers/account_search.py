# intel-monitor/backend/crawlers/account_search.py
"""
Account Search — 微博和 X 平台的用户搜索爬虫

Scenario 1 (profile match): 给定精确 uid/handle/URL → 获取锚点用户画像 → 跨平台搜索相似账号
Scenario 2 (name search):  给定昵称 → 关键词搜索 → 画像展示 (无需相似度匹配)

微博 — 通过 CDP 浏览器内 eval() fetch m.weibo.cn API（自动携带 HttpOnly cookie）
       API: containerid=100103type=3 用户搜索端点
       降级: opencli weibo search → 提取作者 → profile lookup
X   — 通过 Playwright headless 浏览器导航 x.com/search?q={name}&f=user 解析 UserCell 卡片
       降级: opencli twitter profile 精确 handle 匹配
"""
import asyncio
import json
import logging
import re
import shutil
import subprocess as _sp
from dataclasses import dataclass, field
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass
class AccountCandidate:
    platform: str
    platform_uid: str
    nickname: str
    avatar_url: str = ""
    bio: str = ""
    followers_count: int = 0
    profile_url: str = ""
    posts: list[dict] = field(default_factory=list)
    # Scoring fields
    match_score: float = 0.0
    score_detail: dict | None = None
    matched_with: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# CDP Proxy helpers — used by Weibo to evaluate fetch() inside browser tab
# ═══════════════════════════════════════════════════════════════════════════

CDP_PROXY = "http://localhost:3456"


def _cdp_req_sync(method: str, path: str, body: str | None = None, timeout: int = 10) -> str:
    """Synchronous HTTP request to CDP proxy (called via asyncio.to_thread)."""
    import urllib.request as _ur
    data = body.encode("utf-8") if body else None
    req = _ur.Request(f"{CDP_PROXY}{path}", data=data, method=method)
    with _ur.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


async def _cdp_get(path: str, timeout: int = 5) -> str:
    return await asyncio.to_thread(_cdp_req_sync, "GET", path, None, timeout)


async def _cdp_post(path: str, body: str, timeout: int = 10) -> str:
    return await asyncio.to_thread(_cdp_req_sync, "POST", path, body, timeout)


async def _cdp_eval(target_id: str, js: str, timeout: int = 15) -> str:
    """Evaluate JS in a CDP tab. Returns .value field from proxy JSON response."""
    raw = await _cdp_post(f"/eval?target={target_id}", js, timeout)
    if raw:
        try:
            return json.loads(raw).get("value", "")
        except json.JSONDecodeError:
            return raw
    return ""


async def _cdp_new_tab(url: str, timeout: int = 15) -> str:
    raw = await _cdp_post("/new", url, timeout)
    try:
        return json.loads(raw).get("targetId", "")
    except json.JSONDecodeError:
        return ""


async def _cdp_close(target_id: str):
    try:
        await _cdp_get(f"/close?target={target_id}", 3)
    except Exception:
        pass


# ── Weibo CDP tab cache (reuse one tab for all API calls in a task) ──

_weibo_tab: str = ""


async def _get_weibo_cdp_tab() -> str:
    """Get or create a CDP tab on m.weibo.cn for cookie-bearing fetch() calls.

    Reuses an existing tab so we don't create a new one for every API request.
    """
    global _weibo_tab
    if _weibo_tab:
        try:
            info = await _cdp_get(f"/info?target={_weibo_tab}", 3)
            if "url" in (info or ""):
                return _weibo_tab
        except Exception:
            _weibo_tab = ""

    # Find an existing Weibo tab — must be on m.weibo.cn for same-origin fetch()
    try:
        raw = await _cdp_get("/targets", 5)
        targets = json.loads(raw) if raw else []
        for t in targets:
            url = t.get("url", "") or ""
            if "m.weibo.cn" in url:
                _weibo_tab = t.get("targetId", "")
                logger.debug(f"[weibo] Reusing existing m.weibo.cn tab {_weibo_tab[:16]}")
                return _weibo_tab
    except Exception:
        pass

    # Create a new tab
    tid = await _cdp_new_tab("https://m.weibo.cn/", 15)
    if tid:
        await asyncio.sleep(2)  # let cookies propagate
        _weibo_tab = tid
    return _weibo_tab


# ═══════════════════════════════════════════════════════════════════════════
# Weibo — via m.weibo.cn API, called through CDP browser fetch()
# ═══════════════════════════════════════════════════════════════════════════

WEIBO_USER_SEARCH_URL = (
    "https://m.weibo.cn/api/container/getIndex"
    "?containerid=100103type%3D3%26q%3D{query}&page={page}"
)
WEIBO_PROFILE_URL = (
    "https://m.weibo.cn/api/container/getIndex"
    "?type=uid&value={uid}&containerid=100505{uid}"
)
WEIBO_POSTS_URL = (
    "https://m.weibo.cn/api/container/getIndex"
    "?type=uid&value={uid}&containerid=107603{uid}&page={page}"
)


async def _weibo_api_fetch(url: str, timeout_s: int = 15) -> dict | None:
    """Call a m.weibo.cn API inside a CDP browser tab via eval() fetch().

    This is necessary because the SUB cookie is HttpOnly — it cannot be read
    via document.cookie and passed as a header.  Instead we let the browser's
    own fetch() with credentials:'include' send every cookie automatically.

    Returns the parsed JSON on ok=1, None otherwise.
    """
    tid = await _get_weibo_cdp_tab()
    if not tid:
        logger.warning("[weibo] No CDP tab available for API fetch")
        return None

    js = (
        "(async () => {"
        "  try {"
        "    const r = await fetch(" + json.dumps(url) + ", {"
        "      credentials:'include',"
        "      headers:{'X-Requested-With':'XMLHttpRequest','Referer':'https://m.weibo.cn/','Accept':'application/json, text/plain, */*'}"
        "    });"
        "    return await r.text();"
        "  } catch(e) { return JSON.stringify({__error__: e.message}); }"
        "})()"
    )

    raw = await _cdp_eval(tid, js, timeout_s)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"[weibo] API response not valid JSON: {raw[:200]}")
        return None

    if isinstance(data, dict) and data.get("__error__"):
        logger.warning(f"[weibo] fetch error: {data['__error__']}")
        return None
    if data and data.get("ok") == 1:
        return data
    if data and data.get("ok") == 0:
        logger.warning(f"[weibo] API ok=0: {data.get('msg', '')}")

    return None


def _parse_weibo_followers(raw: str | int | float | None) -> int:
    """Parse Weibo follower count which may be '15.7万', '1000', etc."""
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    raw = str(raw).strip()
    if raw.endswith("万"):
        try:
            return int(float(raw[:-1]) * 10000)
        except ValueError:
            return 0
    if raw.endswith("亿"):
        try:
            return int(float(raw[:-1]) * 100_000_000)
        except ValueError:
            return 0
    try:
        return int(raw)
    except ValueError:
        return 0


async def search_weibo_users(name: str, limit: int = 8) -> list[AccountCandidate]:
    """Search Weibo users via the dedicated user search API (type=3).

    Primary:  CDP eval → fetch() to m.weibo.cn API
    Fallback: opencli weibo search → extract authors → profile lookup
    """
    candidates: list[AccountCandidate] = []
    seen_uids: set[str] = set()

    # ── Primary: CDP → m.weibo.cn API ───────────────────────────
    try:
        for page in range(1, 4):
            if len(candidates) >= limit:
                break
            url = WEIBO_USER_SEARCH_URL.format(query=quote(name), page=page)
            data = await _weibo_api_fetch(url)
            if not data:
                break

            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                if len(candidates) >= limit:
                    break
                if card.get("card_type") != 11:  # 11 = user card
                    continue
                card_group = card.get("card_group", [])
                if not card_group:
                    continue
                user = card_group[0].get("user", {})
                uid = str(user.get("id", ""))
                if not uid or uid in seen_uids:
                    continue
                seen_uids.add(uid)
                candidates.append(AccountCandidate(
                    platform="weibo",
                    platform_uid=uid,
                    nickname=user.get("screen_name", ""),
                    avatar_url=user.get("avatar_hd", "") or user.get("profile_image_url", ""),
                    bio=user.get("description", "") or "",
                    followers_count=_parse_weibo_followers(
                        user.get("followers_count") or user.get("followers_count_str")
                    ),
                    profile_url=user.get("profile_url", "") or f"https://weibo.com/u/{uid}",
                ))

            total = data.get("data", {}).get("cardlistInfo", {}).get("total", 0)
            if total == 0 or page * 10 >= total:
                break

    except Exception as e:
        logger.warning(f"[weibo] CDP user search error: {e}")

    if candidates:
        logger.info(f"Weibo user search (CDP): {len(candidates)} for '{name}'")
        return candidates[:limit]

    # ── Fallback: opencli weibo search ───────────────────────────
    return await _search_weibo_users_via_opencli(name, limit)


async def _search_weibo_users_via_opencli(name: str, limit: int) -> list[AccountCandidate]:
    """Fallback: opencli weibo search → extract authors → profile lookup."""
    opencli_path = shutil.which("opencli")
    if not opencli_path:
        return []

    candidates: list[AccountCandidate] = []
    seen_authors: set[tuple[str, str]] = set()

    try:
        args = ["weibo", "search", name, "--limit", "40", "--format", "json"]
        stdout = await asyncio.to_thread(
            lambda: _sp.run([opencli_path] + args, capture_output=True, timeout=90)
        )
        raw = stdout.stdout.decode("utf-8", errors="ignore").strip()
        start = raw.find("[")
        if start >= 0:
            raw = raw[start:]
        data = json.loads(raw) if raw else []
        if not isinstance(data, list):
            data = []

        raw_candidates: list[tuple[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            author = item.get("author", "")
            url = item.get("url", "")
            if not author:
                continue
            uid = ""
            m = re.search(r"weibo\.com/(\d+)/", url)
            if m:
                uid = m.group(1)
            if (author, uid) in seen_authors:
                continue
            seen_authors.add((author, uid))
            raw_candidates.append((author, uid))

        sem = asyncio.Semaphore(5)

        async def lookup_one(author: str, uid: str) -> AccountCandidate | None:
            async with sem:
                try:
                    lookup = uid if uid else author
                    args2 = ["weibo", "user", lookup, "--format", "json"]
                    stdout2 = await asyncio.to_thread(
                        lambda: _sp.run([opencli_path] + args2, capture_output=True, timeout=30)
                    )
                    raw2 = stdout2.stdout.decode("utf-8", errors="ignore").strip()
                    s2 = raw2.find("{")
                    if s2 >= 0:
                        raw2 = raw2[s2:]
                    for end in ["\n  }\n]", "\n}\n"]:
                        e = raw2.find(end)
                        if e > 0:
                            raw2 = raw2[: e + len(end) - 2]
                            break
                    profile = json.loads(raw2) if raw2 else None
                    if profile and isinstance(profile, dict):
                        puid = str(profile.get("uid", "") or uid)
                        return AccountCandidate(
                            platform="weibo",
                            platform_uid=puid or author,
                            nickname=profile.get("screen_name", "") or author,
                            avatar_url=profile.get("avatar_hd", "") or profile.get("avatar", ""),
                            bio=profile.get("description", "") or "",
                            followers_count=profile.get("followers", 0) or profile.get("followers_count", 0),
                            profile_url=profile.get("profile_url", "") or f"https://weibo.com/u/{puid}",
                        )
                except Exception as e:
                    logger.warning(f"[weibo] opencli profile lookup error '{author}': {e}")
                return None

        tasks = [lookup_one(a, u) for a, u in raw_candidates[: limit * 2]]
        for r in await asyncio.gather(*tasks):
            if r:
                candidates.append(r)

    except Exception as e:
        logger.warning(f"[weibo] opencli search error: {e}")

    logger.info(f"Weibo user search (opencli fallback): {len(candidates)} for '{name}'")
    return candidates[:limit]


async def fetch_weibo_user_posts(uid: str, limit: int = 5) -> list[dict]:
    """Fetch recent posts for a Weibo user.

    Primary:  CDP → m.weibo.cn posts API
    Fallback: opencli weibo user-posts
    """
    posts: list[dict] = []

    # ── Primary: CDP → m.weibo.cn API ───────────────────────────
    try:
        url = WEIBO_POSTS_URL.format(uid=uid, page=1)
        data = await _weibo_api_fetch(url)
        if data:
            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                if card.get("card_type") != 9:  # 9 = post
                    continue
                mblog = card.get("mblog", {})
                if not mblog:
                    continue
                posts.append({
                    "text": (mblog.get("text", "") or "").strip(),
                    "created_at": mblog.get("created_at", ""),
                    "likes": mblog.get("attitudes_count", 0) or 0,
                    "comments": mblog.get("comments_count", 0) or 0,
                    "shares": mblog.get("reposts_count", 0) or 0,
                    "url": f"https://m.weibo.cn/detail/{mblog.get('id', '')}",
                })
                if len(posts) >= limit:
                    break

    except Exception as e:
        logger.warning(f"[weibo] CDP posts fetch error: {e}")

    if posts:
        logger.info(f"Weibo posts (CDP): {len(posts)} for uid={uid}")
        return posts[:limit]

    # ── Fallback: opencli weibo user-posts ───────────────────────
    opencli_path = shutil.which("opencli")
    if not opencli_path:
        return []

    try:
        args = ["weibo", "user-posts", uid, "--limit", str(limit), "--format", "json"]
        stdout = await asyncio.to_thread(
            lambda: _sp.run([opencli_path] + args, capture_output=True, timeout=60)
        )
        raw = stdout.stdout.decode("utf-8", errors="ignore").strip()
        start = raw.find("[")
        if start >= 0:
            raw = raw[start:]
        data_list = json.loads(raw) if raw else []
        if not isinstance(data_list, list):
            return posts
        for item in data_list[:limit]:
            if not isinstance(item, dict):
                continue
            posts.append({
                "text": item.get("text", "") or item.get("title", ""),
                "created_at": item.get("created_at", "") or item.get("time", ""),
                "likes": item.get("likes", 0) or item.get("attitudes_count", 0) or 0,
                "comments": item.get("comments", 0) or item.get("comments_count", 0) or 0,
                "shares": item.get("shares", 0) or item.get("reposts_count", 0) or 0,
            })
    except Exception as e:
        logger.warning(f"[weibo] opencli posts error uid={uid}: {e}")

    logger.info(f"Weibo posts (opencli fallback): {len(posts)} for uid={uid}")
    return posts[:limit]


async def get_weibo_user_by_uid_or_url(uid_or_url: str) -> AccountCandidate | None:
    """Get a single Weibo user profile by uid, profile URL, or screen_name.

    Primary:  CDP → m.weibo.cn profile API
    Fallback: opencli weibo user
    """
    lookup = uid_or_url.strip()
    if "weibo.com" in lookup:
        m = re.search(r"weibo\.com/u/(\d+)", lookup)
        if not m:
            m = re.search(r"weibo\.com/(\d+)", lookup)
        if not m:
            m = re.search(r"weibo\.com/n/([^/?]+)", lookup)
            if m:
                lookup = m.group(1)
            else:
                return None
        else:
            lookup = m.group(1)

    # ── Primary: CDP → m.weibo.cn API ───────────────────────────
    try:
        url = WEIBO_PROFILE_URL.format(uid=lookup)
        data = await _weibo_api_fetch(url)
        if data:
            user_info = data.get("data", {}).get("userInfo", {})
            if user_info:
                uid = str(user_info.get("id", "") or lookup)
                return AccountCandidate(
                    platform="weibo",
                    platform_uid=uid,
                    nickname=user_info.get("screen_name", "") or lookup,
                    avatar_url=user_info.get("avatar_hd", "") or user_info.get("profile_image_url", ""),
                    bio=user_info.get("description", "") or "",
                    followers_count=_parse_weibo_followers(
                        user_info.get("followers_count") or user_info.get("followers_count_str")
                    ),
                    profile_url=f"https://weibo.com/u/{uid}",
                )
    except Exception as e:
        logger.warning(f"[weibo] CDP profile error: {e}")

    # ── Fallback: opencli weibo user ─────────────────────────────
    opencli_path = shutil.which("opencli")
    if not opencli_path:
        return None

    try:
        args = ["weibo", "user", lookup, "--format", "json"]
        stdout = await asyncio.to_thread(
            lambda: _sp.run([opencli_path] + args, capture_output=True, timeout=30)
        )
        raw = stdout.stdout.decode("utf-8", errors="ignore").strip()
        s = raw.find("{")
        if s >= 0:
            raw = raw[s:]
        for end in ["\n  }\n]", "\n}\n"]:
            e = raw.find(end)
            if e > 0:
                raw = raw[: e + len(end) - 2]
                break
        profile = json.loads(raw) if raw else None
        if profile and isinstance(profile, dict) and profile.get("uid"):
            uid = str(profile["uid"])
            return AccountCandidate(
                platform="weibo",
                platform_uid=uid,
                nickname=profile.get("screen_name", ""),
                avatar_url=profile.get("avatar_hd", "") or profile.get("avatar", ""),
                bio=profile.get("description", "") or "",
                followers_count=profile.get("followers", 0) or profile.get("followers_count", 0),
                profile_url=profile.get("url", "") or f"https://weibo.com/u/{uid}",
            )
    except Exception as e:
        logger.warning(f"[weibo] opencli profile error '{uid_or_url}': {e}")

    return None


# ═══════════════════════════════════════════════════════════════════════════
# X / Twitter — Playwright headless user search + opencli fallback
# ═══════════════════════════════════════════════════════════════════════════

X_USER_SEARCH_URL = "https://x.com/search?q={query}&f=user"


async def search_x_users(name: str, limit: int = 8) -> list[AccountCandidate]:
    """Search X users via CDP browser → x.com/search?q={name}&f=user.

    X user search page requires login cookies, so we use the user's CDP browser
    (same Chrome that's logged into X).  Falls back to opencli twitter profile
    for exact handle match.
    """
    try:
        result = await _search_x_users_via_cdp(name, limit)
        if result:
            return result
    except Exception as e:
        logger.warning(f"[x] CDP user search error: {e}")

    return await _search_x_via_profile_fallback(name, limit)


async def _search_x_users_via_cdp(name: str, limit: int) -> list[AccountCandidate]:
    """Open a CDP tab to x.com/search?q={name}&f=user and parse UserCell cards."""
    url = X_USER_SEARCH_URL.format(query=quote(name))
    tid = await _cdp_new_tab(url, 20)
    if not tid:
        return []

    candidates: list[AccountCandidate] = []
    try:
        # Wait for page to settle and scroll
        await asyncio.sleep(3)

        for _ in range(5):
            await _cdp_eval(tid, "window.scrollTo(0, document.body.scrollHeight)", 5)
            await asyncio.sleep(0.8)

        users_json = await _cdp_eval(tid, """
            (() => {
                const cells = document.querySelectorAll('[data-testid=UserCell]');
                const users = [];
                cells.forEach(cell => {
                    const anchors = [...cell.querySelectorAll('a[role=link]')];
                    const hrefs = anchors.map(a => a.href);
                    const profileHref = hrefs.find(h =>
                        h.includes('x.com/') && !h.includes('help.x.com')
                    );
                    const handle = profileHref
                        ? profileHref.split('/').pop()?.split('?')[0] || ''
                        : '';
                    const imgs = [...cell.querySelectorAll('img')];
                    const avatar = imgs.find(i => i.src.includes('pbs.twimg.com'))?.src
                        || imgs.find(i => i.src.includes('twimg.com'))?.src
                        || '';
                    const avatarHd = avatar.replace(/_bigger|_normal|_mini/, '_400x400');
                    const text = (cell.innerText || '');
                    const lines = text.split('\\n').filter(l => l.trim());
                    const skipSet = new Set(['Follow', '关注', 'Following']);
                    const filtered = lines.filter(l =>
                        !skipSet.has(l) && !l.startsWith('Translated by') && !l.startsWith('@')
                    );
                    const name = filtered[0] || '';
                    const bio = filtered.slice(1).join(' ').substring(0, 300);
                    users.push({
                        handle, name,
                        avatar: avatarHd || avatar,
                        profileLink: profileHref || '',
                        bio
                    });
                });
                return JSON.stringify(users);
            })()
        """, 15)

        data = json.loads(users_json) if users_json else []
        seen: set[str] = set()
        for u in data or []:
            handle = u.get("handle", "")
            if not handle or handle in seen:
                continue
            if len(candidates) >= limit:
                break
            seen.add(handle)
            candidates.append(AccountCandidate(
                platform="x",
                platform_uid=handle,
                nickname=u.get("name", "") or handle,
                avatar_url=u.get("avatar", ""),
                bio=u.get("bio", ""),
                followers_count=0,
                profile_url=u.get("profileLink", "") or f"https://x.com/{handle}",
            ))

    finally:
        await _cdp_close(tid)

    logger.info(f"X user search (CDP): {len(candidates)} for '{name}'")
    return candidates[:limit]


async def _search_x_via_profile_fallback(name: str, limit: int) -> list[AccountCandidate]:
    """Fallback: opencli twitter profile for exact handle match."""
    opencli_path = shutil.which("opencli")
    if not opencli_path:
        return []

    clean = re.sub(r"[^A-Za-z0-9_]", "", name.lower())
    if not clean or len(clean) < 2:
        return []

    try:
        args = ["twitter", "profile", clean, "--format", "json"]
        stdout = await asyncio.to_thread(
            lambda: _sp.run([opencli_path] + args, capture_output=True, timeout=30)
        )
        raw = stdout.stdout.decode("utf-8", errors="ignore").strip()
        s = raw.find("{")
        if s >= 0:
            raw = raw[s:]
        end = raw.find("\n  }\n]")
        if end > 0:
            raw = raw[: end + 4]
        profile = json.loads(raw) if raw else None
        if profile and isinstance(profile, dict) and profile.get("screen_name"):
            return [AccountCandidate(
                platform="x",
                platform_uid=profile.get("screen_name", ""),
                nickname=profile.get("name", "") or profile.get("screen_name", ""),
                avatar_url=profile.get("profile_image_url", "") or profile.get("profile_image_url_https", ""),
                bio=profile.get("description", "") or profile.get("bio", ""),
                followers_count=profile.get("followers", 0) or profile.get("followers_count", 0),
                profile_url=f"https://x.com/{profile.get('screen_name', '')}",
            )][:limit]
    except Exception:
        pass

    return []


async def get_x_user_by_handle_or_url(handle_or_url: str) -> AccountCandidate | None:
    """Get a single X user profile by handle or URL.

    Primary:  Playwright headless → x.com/{handle}
    Fallback: opencli twitter profile
    """
    lookup = handle_or_url.strip()
    if "x.com/" in lookup or "twitter.com/" in lookup:
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)", lookup)
        if m:
            lookup = m.group(1)
        else:
            return None
    lookup = lookup.lstrip("@")

    try:
        result = await _get_x_profile_via_playwright(lookup)
        if result:
            return result
    except Exception as e:
        logger.warning(f"[x] Playwright profile error for @{lookup}: {e}")

    # Fallback: opencli
    opencli_path = shutil.which("opencli")
    if not opencli_path:
        return None

    try:
        args = ["twitter", "profile", lookup, "--format", "json"]
        stdout = await asyncio.to_thread(
            lambda: _sp.run([opencli_path] + args, capture_output=True, timeout=30)
        )
        raw = stdout.stdout.decode("utf-8", errors="ignore").strip()
        s = raw.find("{")
        if s >= 0:
            raw = raw[s:]
        end = raw.find("\n  }\n]")
        if end > 0:
            raw = raw[: end + 4]
        profile = json.loads(raw) if raw else None
        if profile and isinstance(profile, dict) and profile.get("screen_name"):
            return AccountCandidate(
                platform="x",
                platform_uid=profile.get("screen_name", ""),
                nickname=profile.get("name", "") or profile.get("screen_name", ""),
                avatar_url=profile.get("profile_image_url", "") or profile.get("profile_image_url_https", ""),
                bio=profile.get("description", "") or profile.get("bio", ""),
                followers_count=profile.get("followers", 0) or profile.get("followers_count", 0),
                profile_url=f"https://x.com/{profile.get('screen_name', '')}",
            )
    except Exception as e:
        logger.warning(f"[x] opencli profile error '{handle_or_url}': {e}")

    return None


async def _get_x_profile_via_playwright(handle: str) -> AccountCandidate | None:
    """Navigate to x.com/{handle} and extract profile from DOM."""
    from playwright.async_api import async_playwright
    from pathlib import Path

    user_data_dir = Path("backend/data/x_profile")
    user_data_dir.mkdir(parents=True, exist_ok=True)

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
            await page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(1)

            data = json.loads(await page.evaluate("""
                (handle) => {
                    const avatarImg = document.querySelector('img[src*="pbs.twimg.com/profile"]');
                    const nameEl = document.querySelector('[data-testid="UserName"]');
                    const bioEl = document.querySelector('[data-testid="UserDescription"]');
                    return JSON.stringify({
                        name: nameEl ? nameEl.innerText.split('\\\\n')[0] : '',
                        avatar: avatarImg ? avatarImg.src.replace(/_bigger|_normal|_mini/, '_400x400') : '',
                        bio: bioEl ? bioEl.innerText : '',
                        handle
                    });
                }
            """, handle))

            if data.get("handle"):
                return AccountCandidate(
                    platform="x",
                    platform_uid=data["handle"],
                    nickname=data.get("name", "") or data["handle"],
                    avatar_url=data.get("avatar", ""),
                    bio=data.get("bio", ""),
                    followers_count=0,
                    profile_url=f"https://x.com/{data['handle']}",
                )
        finally:
            await context.close()

    return None


async def fetch_x_user_posts(handle: str, limit: int = 5) -> list[dict]:
    """Fetch recent posts for an X user via opencli twitter tweets.

    opencli 'twitter tweets' is reliable for post content and reuses the
    existing Chrome login session — no new browser window needed here
    since X post content doesn't require the user search approach.
    """
    opencli_path = shutil.which("opencli")
    if not opencli_path:
        return []
    posts = []
    try:
        args = ["twitter", "tweets", handle, "--limit", str(limit), "--format", "json"]
        stdout = await asyncio.to_thread(
            lambda: _sp.run([opencli_path] + args, capture_output=True, timeout=60)
        )
        raw = stdout.stdout.decode("utf-8", errors="ignore").strip()
        start = raw.find("[")
        if start >= 0:
            raw = raw[start:]
        data = json.loads(raw) if raw else None
        if not data or not isinstance(data, list):
            return posts
        for item in data:
            if not isinstance(item, dict):
                continue
            posts.append({
                "text": item.get("text", ""),
                "created_at": item.get("created_at", ""),
                "likes": item.get("likes", 0) or 0,
                "comments": item.get("replies", 0) or 0,
                "shares": item.get("retweets", 0) or 0,
                "url": item.get("url", ""),
            })
    except Exception as e:
        logger.warning(f"X fetch posts error for @{handle}: {e}")
    return posts
