# intel-monitor/backend/services/account_matcher.py
"""
Account Matcher — 账号比对核心编排逻辑

Scenario 1 (match_mode="profile"):
  给定 uid/handle/URL → 获取锚点用户 + 发帖 → AI 画像
  → 提取锚点用户昵称 → 跨平台搜索相似昵称 → 画像
  → 以锚点画像为基准打分（内容相似度 40%、昵称相似度 25%、时间模式 15%、AI 20%）
  → 返回 Top 5

Scenario 2 (match_mode="nickname"):
  给定昵称 → 跨平台搜索 → 抓帖 → AI 画像
  → 按昵称相似度排序，展示所有候选人（不需要配对打分）

评分维度：
- 昵称相似度 — 编辑距离 + 中文字符重叠
- 内容主题相似度 — AI 画像关键词交集 + 领域/语调匹配
- 发帖时间模式 — 相同活跃时段
- AI 综合判断 — DeepSeek 逐对打分
"""
import asyncio
import json
import logging
import hashlib
import re
from datetime import datetime
from itertools import combinations

from sqlalchemy import select, delete
from database import async_session
from models.account_match import AccountMatchTask, AccountMatchCandidate, AccountMatchResult
from crawlers.account_search import (
    AccountCandidate,
    search_weibo_users, fetch_weibo_user_posts,
    search_x_users, fetch_x_user_posts,
    get_weibo_user_by_uid_or_url, get_x_user_by_handle_or_url,
)

logger = logging.getLogger(__name__)

CANDIDATES_PER_PLATFORM = 8

PLATFORM_SEARCHERS = {
    "weibo": (search_weibo_users, fetch_weibo_user_posts),
    "x": (search_x_users, fetch_x_user_posts),
}

# Profile match scoring weights — configurable per dimension
PROFILE_MATCH_WEIGHTS = {
    "name_similarity": 0.25,
    "time_pattern": 0.15,
    "content_similarity": 0.40,
    "ai_judgment": 0.20,
}


async def run_account_match(
    task_id: int,
    target_name: str,
    platforms: list[str],
    match_mode: str = "nickname",
    anchor_platform: str | None = None,
):
    """Background task: orchestrates the full matching pipeline."""
    async with async_session() as db:
        task = await db.get(AccountMatchTask, task_id)
        if not task:
            return

        task.match_mode = match_mode
        await db.commit()

        error_log = {}

        if match_mode == "profile":
            await _run_scenario_profile(task, target_name, platforms, error_log, db, anchor_platform)
        else:
            await _run_scenario_nickname(task, target_name, platforms, error_log, db)


# ── Scenario 1: Profile-based cross-platform matching ────────────────────


async def _run_scenario_profile(task, target_name, platforms, error_log, db, anchor_platform: str | None = None):
    """Given a uid/handle/URL, find similar accounts across platforms."""
    task.status = "fetching_anchor"
    await db.commit()

    # Step 1: Resolve anchor user — try anchor_platform first, then fall back to the
    # remaining platforms so a wrong platform choice doesn't hard-fail the task.
    anchor = None
    anchor_platforms = ([anchor_platform] if anchor_platform else []) + [
        p for p in (platforms or []) if p != anchor_platform
    ]
    if not anchor_platforms:
        anchor_platforms = ["weibo", "x"]
    for platform in anchor_platforms:
        task.status = f"fetching_anchor:{platform}"
        await db.commit()
        try:
            if platform == "weibo":
                anchor = await get_weibo_user_by_uid_or_url(target_name)
            elif platform == "x":
                anchor = await get_x_user_by_handle_or_url(target_name)
            else:
                error_log[f"anchor_{platform}"] = f"Unsupported anchor platform: {platform}"
                continue
        except Exception as e:
            error_log[f"anchor_{platform}"] = str(e)
            logger.warning(f"Anchor fetch error [{platform}]: {e}")
        if anchor:
            break
        error_log[f"anchor_{platform}"] = (
            f"could not resolve user from input {target_name!r} "
            f"(no exception, resolver returned None)"
        )

    if not anchor:
        task.status = "failed"
        task.error_log = json.dumps(
            error_log or {"anchor": "Could not resolve user from input"},
            ensure_ascii=False,
        )
        task.completed_at = datetime.utcnow()
        await db.commit()
        return

    # Step 2: Fetch anchor posts + AI profile
    task.status = "fetching_posts"
    await db.commit()

    anchor_fetcher = PLATFORM_SEARCHERS.get(anchor.platform, (None, None))[1]
    if anchor_fetcher:
        anchor.posts = await anchor_fetcher(anchor.platform_uid)
    anchor_profile = await _ai_generate_profile(anchor) if anchor.posts else None

    task.anchor_profile_json = (
        json.dumps(anchor_profile, ensure_ascii=False) if anchor_profile else None
    )
    await db.commit()

    # Step 3: Generate search keywords from anchor user
    # Use anchor nickname + any multi-char substrings as search terms
    search_names = _generate_search_names(anchor.nickname)

    # Search both platforms for similar names
    task.status = "searching"
    await db.commit()

    all_candidates = []
    seen_uids = set()
    seen_uids.add(f"{anchor.platform}:{anchor.platform_uid}")  # exclude anchor itself

    for platform in platforms:
        for sname in search_names[:3]:  # limit to top 3 search variants
            if len(all_candidates) >= CANDIDATES_PER_PLATFORM * 2:
                break
            try:
                searcher_fn = PLATFORM_SEARCHERS.get(platform, (None, None))[0]
                if not searcher_fn:
                    continue
                candidates = await searcher_fn(sname, limit=8)
                for c in candidates:
                    key = f"{c.platform}:{c.platform_uid}"
                    if key not in seen_uids:
                        seen_uids.add(key)
                        all_candidates.append(c)
            except Exception as e:
                logger.warning(f"Search error [{platform}][{sname}]: {e}")

    if not all_candidates:
        task.status = "failed"
        task.error_log = "No similar accounts found"
        task.completed_at = datetime.utcnow()
        await db.commit()
        return

    # Step 4: Fetch posts + AI profile for all candidates
    task.status = "fetching_posts"
    await db.commit()
    await _fetch_and_profile_all(all_candidates)

    # Step 5: Calculate heuristic scores first, then call DeepSeek for AI judgment
    task.status = "comparing"
    await db.commit()

    # 5a: Compute per-candidate heuristic scores (3 dimensions)
    heuristic_scores: list[dict] = []
    for c in all_candidates:
        name_sim = _name_similarity(c.nickname, anchor.nickname)
        content_sim = _content_similarity_vs_profile(c, anchor_profile)
        time_sim = _time_pattern_similarity(c, anchor)
        dims = {
            "name_similarity": round(name_sim, 4),
            "content_similarity": round(content_sim, 4),
            "time_pattern_similarity": round(time_sim, 4),
        }
        heuristic_scores.append(dims)
        c.score_detail = dims
        c.matched_with = anchor.nickname

    # 5b: Call DeepSeek for AI judgment on each candidate vs anchor
    task.status = "ai_scoring"
    await db.commit()
    ai_scores = await _ai_score_candidates_vs_anchor(
        candidates=all_candidates,
        anchor=anchor,
        anchor_profile=anchor_profile,
        heuristic_scores=heuristic_scores,
        weights=PROFILE_MATCH_WEIGHTS,
    )

    # 5c: Merge AI scores into final weighted score
    for i, c in enumerate(all_candidates):
        dims = c.score_detail
        ai_s = ai_scores[i] if i < len(ai_scores) else 0.5  # fallback to neutral
        dims["ai_judgment"] = round(ai_s, 4)
        w = PROFILE_MATCH_WEIGHTS
        weighted = (
            dims["name_similarity"] * w["name_similarity"]
            + dims["time_pattern_similarity"] * w["time_pattern"]
            + dims["content_similarity"] * w["content_similarity"]
            + ai_s * w["ai_judgment"]
        )
        c.match_score = round(weighted, 4)
        c.score_detail = dims

    # Step 6: Persist — include anchor as the first result
    # Add anchor to candidates list for display (as #0)
    anchor.match_score = 1.0
    anchor.score_detail = {"name_similarity": 1.0, "content_similarity": 1.0, "time_pattern_similarity": 1.0, "ai_judgment": 1.0}
    anchor.matched_with = "(参照账号)"
    anchor._profile = anchor_profile
    all_candidates.insert(0, anchor)

    db_candidates = await _persist_candidates(all_candidates, task.id, db)

    # Build results — top 5 (anchor + top 4 matches)
    match_results = _build_top_matches_single_platform(all_candidates, top_n=6)

    await _persist_results(match_results, db_candidates, task.id, db)

    task.status = "completed"
    task.total_candidates = len(db_candidates)
    task.total_groups = len(match_results)
    task.completed_at = datetime.utcnow()
    await db.commit()

    logger.info(
        f"AccountMatchTask {task.id} completed (profile): "
        f"anchor=@{anchor.nickname}, {len(db_candidates)} candidates, "
        f"{len(match_results)} groups"
    )


# ── Scenario 2: Nickname-based search with profiles ──────────────────────


async def _run_scenario_nickname(task, target_name, platforms, error_log, db):
    """Given a nickname, search all platforms and return profiled candidates."""
    # Step 1: Search
    task.status = "searching"
    await db.commit()

    all_candidates = []
    for platform in platforms:
        searcher_fn, _ = PLATFORM_SEARCHERS.get(platform, (None, None))
        if not searcher_fn:
            error_log[platform] = f"Unsupported platform: {platform}"
            continue
        try:
            candidates = await searcher_fn(target_name, limit=CANDIDATES_PER_PLATFORM)
            logger.info(f"[{platform}] Found {len(candidates)} candidates")
            all_candidates.extend(candidates)
        except Exception as e:
            error_log[platform] = str(e)
            logger.exception(f"[{platform}] Search error")

    if not all_candidates:
        task.status = "failed"
        task.error_log = (
            json.dumps(error_log, ensure_ascii=False)
            if error_log else "No candidates found"
        )
        task.completed_at = datetime.utcnow()
        await db.commit()
        return

    # Step 2: Fetch posts + AI profile
    task.status = "fetching_posts"
    await db.commit()
    await _fetch_and_profile_all(all_candidates)

    # Step 3: Score by name similarity only (Scenario 2 — no anchor profile)
    task.status = "comparing"
    await db.commit()

    for c in all_candidates:
        dims = {
            "name_similarity": round(_name_similarity(c.nickname, target_name), 4),
            "content_similarity": 0.0,
            "time_pattern_similarity": 0.5,
        }
        weighted = dims["name_similarity"] * 0.40 + 0.5 * 0.10 + 0.5 * 0.50  # rest neutral
        c.match_score = round(weighted, 4)
        c.score_detail = dims

    # Step 4: Persist
    db_candidates = await _persist_candidates(all_candidates, task.id, db)

    match_results = _build_top_matches_single_platform(all_candidates)

    await _persist_results(match_results, db_candidates, task.id, db)

    task.status = "completed"
    task.total_candidates = len(db_candidates)
    task.total_groups = len(match_results)
    task.completed_at = datetime.utcnow()
    await db.commit()


# ── Shared helpers ────────────────────────────────────────────────────────


async def _fetch_and_profile_all(candidates: list[AccountCandidate]):
    """Fetch posts + AI profile for all candidates concurrently."""
    sem = asyncio.Semaphore(5)

    async def _bounded_fetch(c: AccountCandidate):
        async with sem:
            _, fetcher_fn = PLATFORM_SEARCHERS.get(c.platform, (None, None))
            if fetcher_fn:
                try:
                    c.posts = await fetcher_fn(c.platform_uid)
                except Exception as e:
                    logger.warning(f"Fetch posts error [{c.platform}@{c.nickname}]: {e}")

    await asyncio.gather(*(_bounded_fetch(c) for c in candidates))

    # AI profile in parallel
    async def _profile_one(c: AccountCandidate):
        if c.posts:
            try:
                profile = await _ai_generate_profile(c)
                c._profile = profile
            except Exception as e:
                logger.warning(f"AI profile error [{c.nickname}]: {e}")

    await asyncio.gather(*(_profile_one(c) for c in candidates))


async def _persist_candidates(
    all_candidates: list[AccountCandidate], task_id: int, db
) -> list[AccountMatchCandidate]:
    """Persist candidates to DB, return DB objects."""
    db_candidates = []
    for c in all_candidates:
        dbc = AccountMatchCandidate(
            task_id=task_id,
            platform=c.platform,
            platform_uid=c.platform_uid,
            nickname=c.nickname,
            avatar_url=c.avatar_url,
            bio=c.bio,
            followers_count=c.followers_count,
            profile_url=c.profile_url,
            profile_json=json.dumps(getattr(c, "_profile", None) or {}, ensure_ascii=False),
            posts_json=json.dumps(c.posts, ensure_ascii=False) if c.posts else None,
            match_score=c.match_score,
            score_detail_json=json.dumps(c.score_detail, ensure_ascii=False)
            if c.score_detail else None,
            matched_with=c.matched_with or "",
        )
        db.add(dbc)
        db_candidates.append(dbc)
    await db.flush()
    return db_candidates


async def _persist_results(
    match_results: list[dict],
    db_candidates: list[AccountMatchCandidate],
    task_id: int,
    db,
):
    """Persist match results to DB."""
    for result in match_results:
        member_ids = []
        for ref in result.get("members", []):
            for dc in db_candidates:
                if dc.platform_uid == ref or dc.nickname == ref:
                    member_ids.append(dc.id)
                    break
        if not member_ids:
            continue

        db_result = AccountMatchResult(
            task_id=task_id,
            group_label=result.get("group", ""),
            confidence_score=result.get("score", 0.0),
            account_ids_json=json.dumps(member_ids, ensure_ascii=False),
            ai_analysis=result.get("reason", ""),
            score_detail=json.dumps(result.get("score_detail", {}), ensure_ascii=False)
            if result.get("score_detail") else None,
        )
        db.add(db_result)
    await db.flush()


# ── Scoring functions ─────────────────────────────────────────────────────


def _generate_search_names(nickname: str) -> list[str]:
    """Generate search keyword variants from a nickname."""
    names = [nickname]
    # Remove emoji / special chars
    clean = re.sub(r"[^\w一-鿿\s]", "", nickname).strip()
    if clean and clean != nickname:
        names.append(clean)
    # Split on common separators
    parts = re.split(r"[\s_-]+", nickname)
    if len(parts) > 1:
        names.extend([p for p in parts if len(p) >= 2])
    return list(dict.fromkeys(names))  # dedup, preserve order


def _content_similarity_vs_profile(c: AccountCandidate, anchor_profile: dict | None) -> float:
    """Compare candidate's AI profile against anchor profile."""
    if not anchor_profile or not hasattr(c, "_profile"):
        return 0.0
    c_profile = getattr(c, "_profile", None) or {}
    aw = set((anchor_profile.get("domain", "") + " " + " ".join(anchor_profile.get("keywords", []))).lower().split())
    cw = set((c_profile.get("domain", "") + " " + " ".join(c_profile.get("keywords", []))).lower().split())
    kw_sim = len(aw & cw) / max(len(aw | cw), 1) if aw or cw else 0.0
    domain_sim = 1.0 if anchor_profile.get("domain") == c_profile.get("domain") and anchor_profile.get("domain") else 0.0
    tone_sim = 1.0 if anchor_profile.get("tone") == c_profile.get("tone") and anchor_profile.get("tone") else 0.0
    lang_sim = 1.0 if anchor_profile.get("lang") == c_profile.get("lang") and anchor_profile.get("lang") else 0.0
    return kw_sim * 0.4 + domain_sim * 0.25 + tone_sim * 0.15 + lang_sim * 0.2


# ── Reuse existing scoring primitives from earlier implementation ─────────


def _levenshtein(s1: str, s2: str) -> float:
    if not s1 or not s2:
        return 0.0
    m, n = len(s1), len(s2)
    if m == 0 and n == 0:
        return 1.0
    if m < n:
        s1, s2, m, n = s2, s1, n, m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i]
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return 1.0 - (prev[n] / max(m, n))


def _common_chinese_chars(s1: str, s2: str) -> float:
    set1 = set(re.findall(r"[一-鿿]", s1))
    set2 = set(re.findall(r"[一-鿿]", s2))
    if not set1 and not set2:
        return 0.5
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)


def _name_similarity(n1: str, n2: str) -> float:
    if not n1 or not n2:
        return 0.0
    n1, n2 = n1.lower().lstrip("@"), n2.lower().lstrip("@")
    if n1 == n2:
        return 1.0
    edit = _levenshtein(n1, n2)
    cn = _common_chinese_chars(n1, n2)
    has_cn = bool(re.search(r"[一-鿿]", n1)) and bool(re.search(r"[一-鿿]", n2))
    return cn * 0.6 + edit * 0.4 if has_cn else edit


def _time_pattern_similarity(ca: AccountCandidate, cb: AccountCandidate) -> float:
    hours_a = []
    hours_b = []
    for p in ca.posts or []:
        h = _extract_hour(p.get("created_at", ""))
        if h is not None:
            hours_a.append(h)
    for p in cb.posts or []:
        h = _extract_hour(p.get("created_at", ""))
        if h is not None:
            hours_b.append(h)
    if not hours_a or not hours_b:
        return 0.5

    def classify(hours):
        zones = set()
        for h in hours:
            if 6 <= h <= 11:
                zones.add("morning")
            elif 12 <= h <= 17:
                zones.add("afternoon")
            elif 18 <= h <= 23:
                zones.add("evening")
            else:
                zones.add("night")
        return zones

    za, zb = classify(hours_a), classify(hours_b)
    return len(za & zb) / max(len(za | zb), 1) if za and zb else 0.5


def _extract_hour(ts: str) -> int | None:
    if not ts:
        return None
    m = re.search(r"(\d{2}):(\d{2}):(\d{2})", ts)
    if not m:
        m = re.search(r"T(\d{2}):(\d{2})", ts)
    if not m:
        m = re.search(r"(\d{1,2}):(\d{2})", ts)
    return int(m.group(1)) if m else None


# ── AI helpers ────────────────────────────────────────────────────────────


async def _ai_score_candidates_vs_anchor(
    candidates: list[AccountCandidate],
    anchor: AccountCandidate,
    anchor_profile: dict | None,
    heuristic_scores: list[dict],
    weights: dict,
) -> list[float]:
    """Send anchored candidate profiles + heuristic scores + weights to DeepSeek.

    DeepSeek receives the full context — anchor profile, per-candidate profile,
    pre-computed heuristic scores, and the weight breakdown — and returns a
    0-1 AI judgment for each candidate. The caller blends this score into the
    final weighted formula at the ai_judgment slot (default 20%).

    Returns a list of floats aligned 1:1 with `candidates` (same order).
    """
    if not anchor_profile:
        logger.warning("[account_matcher] No anchor profile, skipping AI scoring")
        return [0.5] * len(candidates)

    from services.summarizer import summarizer

    # ── Build the prompt ──────────────────────────────────────────────
    anchor_text = json.dumps(anchor_profile, ensure_ascii=False)

    entries: list[str] = [
        f"锚点账号 | [{anchor.platform}] {anchor.nickname} (@{anchor.platform_uid})\n"
        f"  简介: {anchor.bio or '无'}\n  画像: {anchor_text}"
    ]

    for i, c in enumerate(candidates):
        profile = getattr(c, '_profile', None) or {}
        profile_text = json.dumps(profile, ensure_ascii=False) if profile else "无画像"
        dims = heuristic_scores[i] if i < len(heuristic_scores) else {}
        posts_sample = ""
        if c.posts:
            samples = [
                (p.get('text', '') or '')[:120]
                for p in c.posts[:3]
                if (p.get('text', '') or '').strip()
            ]
            if samples:
                posts_sample = "\n  近期发帖: " + " | ".join(samples)
        entries.append(
            f"候选人 {i} | [{c.platform}] {c.nickname} (@{c.platform_uid})\n"
            f"  粉丝: {c.followers_count} | 简介: {c.bio or '无'}\n"
            f"  画像: {profile_text}\n"
            f"  启发式评分: 昵称相似度={dims.get('name_similarity', 0):.2%} "
            f"内容相似度={dims.get('content_similarity', 0):.2%} "
            f"时间模式={dims.get('time_pattern_similarity', 0):.2%}{posts_sample}"
        )

    candidates_text = "\n---\n".join(entries)

    weight_desc = (
        f"昵称相似度={weights['name_similarity']:.0%} "
        f"时间模式={weights['time_pattern']:.0%} "
        f"内容相似度={weights['content_similarity']:.0%} "
        f"AI判断={weights['ai_judgment']:.0%}"
    )

    system_prompt = (
        "你是一个跨平台身份关联分析专家。你的任务是比对锚点账号与每个候选账号，"
        "判断它们是否属于同一个人/同一个实体。"
        "你需要综合考量：昵称命名风格、关注领域与关键词重叠、语言风格与语气、"
        "发帖时间规律、粉丝量级等多个维度。"
        "严格输出JSON数组格式，不要包含任何额外文本或markdown标记。"
    )

    user_prompt = (
        f"以下是一个锚点账号（参照账号）和 {len(candidates)} 个候选账号的画像信息。"
        f"请逐一判断每位候选人与锚点账号是否是同一个人/同一实体。\n\n"
        f"最终评分权重参考: {weight_desc}\n"
        f"注：启发式评分仅作为机器参考值供你交叉验证，"
        f"你的判断可以推翻启发式评分（例如昵称完全不同但内容高度重合可给高分，"
        f"或昵称相似但内容领域完全不同则给低分）。\n\n"
        f"{candidates_text}\n\n"
        "请输出JSON数组，每个元素包含：\n"
        '  "candidate_id": 候选人的序号（如"0", "1", "2"），字符串类型\n'
        '  "score": 0-1的置信度（1=完全确定是同一人，0=确定不是）\n'
        '  "reason": 判断理由（中文，50字以内）\n'
        "直接输出JSON数组:"
    )

    # ── Call DeepSeek ────────────────────────────────────────────────
    try:
        api_key, api_url, model, parser, auth_style = summarizer._get_provider_config("deepseek")
        if not api_key:
            logger.warning("[account_matcher] DeepSeek API key not configured, using neutral AI scores")
            return [0.5] * len(candidates)

        logger.info(
            f"[account_matcher] Calling DeepSeek for per-candidate AI judgment: "
            f"{len(candidates)} candidates vs anchor @{anchor.nickname}"
        )
        response = await summarizer._call_provider(
            "deepseek", api_key, api_url, model, parser, auth_style,
            system_prompt, user_prompt,
        )
        if not response:
            logger.warning("[account_matcher] AI scoring returned empty response")
            return [0.5] * len(candidates)

        # Parse JSON array from response
        j_start, j_end = response.find("["), response.rfind("]") + 1
        if j_start >= 0 and j_end > j_start:
            ai_results = json.loads(response[j_start:j_end])
            logger.info(f"[account_matcher] AI scoring result: {len(ai_results)} entries")
        else:
            # Fallback: try single object
            j_start, j_end = response.find("{"), response.rfind("}") + 1
            if j_start >= 0 and j_end > j_start:
                obj = json.loads(response[j_start:j_end])
                ai_results = [obj] if isinstance(obj, dict) else []
            else:
                logger.warning(f"[account_matcher] Could not parse AI response: {response[:200]}")
                return [0.5] * len(candidates)

        # ── Map results back to candidate indices ────────────────────
        score_map: dict[int, float] = {}
        reason_map: dict[int, str] = {}
        for entry in ai_results:
            cid = int(entry.get("candidate_id", -1))
            score = max(0.0, min(1.0, float(entry.get("score", 0.5))))
            reason = entry.get("reason", "")[:60]
            score_map[cid] = score
            reason_map[cid] = reason

        # Build list aligned with candidates
        result: list[float] = []
        for i, c in enumerate(candidates):
            ai_score = score_map.get(i, 0.5)
            if i in reason_map:
                c._ai_reason = reason_map[i]  # stash for persistence/display
            result.append(ai_score)

        logger.info(
            f"[account_matcher] AI scores range: "
            f"min={min(result):.3f}, max={max(result):.3f}, mean={sum(result)/len(result):.3f}"
        )
        return result

    except Exception as e:
        logger.warning(f"[account_matcher] AI scoring error: {e}")
        return [0.5] * len(candidates)


async def _ai_generate_profile(candidate: AccountCandidate) -> dict | None:
    """Generate a structured user profile from the candidate's posts."""
    from services.summarizer import summarizer

    posts_text = "\n".join([
        f"[{i + 1}] {p.get('text', '')[:300]}"
        for i, p in enumerate(candidate.posts[:5])
    ])
    if not posts_text.strip():
        return None

    system_prompt = (
        "你是一个用户画像分析专家。根据以下社交媒体账号的发帖内容，输出该用户的画像JSON。"
        "严格输出JSON格式，不要包含任何额外文本或markdown标记。"
    )
    user_prompt = (
        f"平台: {candidate.platform}\n"
        f"昵称: {candidate.nickname}\n"
        f"简介: {candidate.bio or '无'}\n"
        f"发帖内容:\n{posts_text}\n\n"
        '请输出JSON，包含以下字段：\n'
        '  "domain": 主要关注领域（中文，如"科技/AI"、"娱乐/明星"、"财经"等）\n'
        '  "tone": 语言风格（如"技术分享型"、"生活记录型"、"营销推广型"等）\n'
        '  "lang": 主要语言（"zh"/"en"/"ja"等）\n'
        '  "activity_level": 活跃度（"高"/"中"/"低"）\n'
        '  "keywords": 3-5个关键词数组\n'
        '  "summary": 一句话概括（中文，30字以内）\n'
        "直接输出JSON:"
    )

    try:
        response = await summarizer._call_ai(system_prompt, user_prompt)
        if not response:
            return None
        j_start, j_end = response.find("{"), response.rfind("}") + 1
        return json.loads(response[j_start:j_end]) if j_start >= 0 and j_end > j_start else None
    except Exception as e:
        logger.warning(f"AI profile parse error: {e}")
        return None


# ── Result builder ────────────────────────────────────────────────────────


def _build_top_matches_single_platform(all_candidates: list, top_n: int = 5) -> list[dict]:
    """Return top-N candidates by match_score as individual results."""
    scored = sorted(all_candidates, key=lambda c: c.match_score, reverse=True)
    results = []
    for c in scored[: min(top_n, len(scored))]:
        dims = c.score_detail or {}
        # Distinguish anchor vs match in the label
        label = f"🔗 参照: {c.nickname}" if c.matched_with == "(参照账号)" else c.nickname
        # Build reason line: include AI judgment if present
        ai_s = dims.get("ai_judgment")
        reason_parts = [f"匹配度 {c.match_score:.0%}"]
        if ai_s is not None and ai_s != 0.5:
            reason_parts.append(f"AI {ai_s:.0%}")
        reason_parts.append(f"昵称 {dims.get('name_similarity', 0):.0%}")
        results.append({
            "group": label[:100],
            "score": round(c.match_score, 4),
            "score_detail": dims,
            "members": [c.platform_uid or c.nickname],
            "reason": " | ".join(reason_parts),
        })
    return results
