# intel-monitor/backend/services/risk.py
"""监测贴文风险筛选与分析（飞书推送专用）。

筛选规则（保留风险等级"中"及以上的贴文）：
1. 涉及国家领导人的帖子；
2. 涉及中国与亚洲其他国家（尤其是东南亚）负面内容的帖子。

本地模型上下文不足时的策略：分段分析——贴文按块（每块 ≤15 条 / ≤4000 字）
分别做风险分类，最后对筛出的重要贴文单独生成总摘要（两阶段 AI 调用）。

推送格式：
发帖时间范围 / 发帖数量 / AI摘要 / 重要贴文列表
（风险等级、标题、链接、摘要、时间、来源、作者、情感倾向、提及关键词）
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from services.summarizer import summarizer

logger = logging.getLogger(__name__)

TZ_UTC = timezone.utc
TZ_SHANGHAI = timezone(timedelta(hours=8))

PLATFORM_LABELS = {
    "x": "X (Twitter)",
    "youtube": "YouTube",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "weibo": "微博",
    "toutiao": "今日头条",
    "108community": "108天台社区",
    "facebook": "Facebook",
}

# 分段参数：每块最多贴文数 / 每块最多字符数
_CHUNK_MAX_POSTS = 10
_CHUNK_MAX_CHARS = 4000
# 参与风险分类的贴文上限（超出部分为更早的贴文，通常不重要）
_MAX_POSTS = 80
_CONTENT_CHARS = 250

# 阶段一：逐块风险分类。竖线分隔的纯文本格式（不含括号/大括号，
# 避免本地 VLM 服务把内容里的数组误判为多模态 content 数组导致 400）。
RISK_SYSTEM_PROMPT = (
    "你是社交媒体情报风险分析专家。对给出的贴文逐条分析风险。\n"
    "风险等级判定（从严，拿不准一律视为低，宁缺毋滥）：\n"
    "1. 高危：贴文明确点名国家领导人（姓名、职务，或总书记、主席、总统等明确代称），"
    "或明确涉及中国与亚洲其他国家（尤其是东南亚国家）之间的负面事件、冲突、指责、攻击；\n"
    "2. 中：未点名但隐喻指向国家领导人，或涉及中国与亚洲其他国家关系的敏感政治话题；\n"
    "3. 低：生活、旅游、情感、娱乐、普通社会新闻等不涉及上述政治内容的贴文，一律为低。\n"
    "只输出中/高风险贴文，每行一条，固定 5 个字段，格式为：序号|风险等级|情感倾向|关键词1,关键词2|一句话总结\n"
    "字段顺序不得更改；关键词之间用逗号分隔；一句话总结不超过100字，提炼要点，一段话；总结中不要使用竖线。\n"
    "不要输出任何其他文字，不要 JSON，不要任何括号。没有中高风险贴文时只输出：无\n"
    "情感倾向只按贴文本身情绪判断：明确的冲突、抗议、攻击、批评、丑闻类内容标为负面，"
    "生活、旅游、中性叙述标为中性。不要因为话题敏感就标负面。"
    "关键词给出 2-5 个：贴文中出现的人名、地名、机构、事件名。"
    "序号必须严格对应输入贴文的序号，不得错位。"
)

# 阶段二：重要贴文汇总（300 字以内，总结性为主）
SUMMARY_SYSTEM_PROMPT = (
    "你是社交媒体情报分析专家。基于给出的中高风险贴文，写一段不超过300字的总结。"
    "提炼要点，总结性为主，概括核心议题（政治、国家领导人、涉华与亚洲国家关系）与隐含隐喻，"
    "一段话成文，不要分节、不要小标题、不要编号列表。"
)

_SUMMARY_MAX_CHARS = 300


def _truncate_summary(text: str, limit: int = _SUMMARY_MAX_CHARS) -> str:
    """超长摘要截断：优先在句子边界截断，找不到则硬截。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("。", "！", "？", "；", "\n"):
        pos = cut.rfind(sep)
        if pos >= limit // 2:
            return cut[:pos + 1]
    return cut + "…"


def _excerpt(text: str, n: int) -> str:
    """折叠空白并截取前 n 个字符。"""
    return " ".join(str(text or "").split())[:n]


# ── 确定性硬门槛：用户规则「涉及国家领导人 / 中国与亚洲其他国家（尤其东南亚）负面」──
# AI 分类后的候选贴文必须命中至少一类信号，否则视为误报丢弃。
_LEADER_HINTS = (
    "习近平", "总书记", "国家主席", "主席", "总理", "总统", "首相", "国王", "女王",
    "领导人", "政要", "首脑", "普京", "金正恩", "特朗普", "拜登", "泽连斯基",
)
_ASIA_HINTS = (
    "蒙古", "越南", "泰国", "缅甸", "菲律宾", "印度尼西亚", "印尼", "马来西亚",
    "新加坡", "老挝", "柬埔寨", "文莱", "东帝汶", "日本", "韩国", "朝鲜",
    "印度", "巴基斯坦", "孟加拉", "斯里兰卡", "尼泊尔", "不丹", "阿富汗",
    "哈萨克", "乌兹别克", "吉尔吉斯", "塔吉克", "土库曼", "伊朗", "伊拉克",
    "沙特", "阿联酋", "卡塔尔", "科威特", "以色列", "巴勒斯坦", "土耳其",
    "台湾", "香港",
)
_CHINA_HINTS = ("中国", "中共", "中资", "中国人", "北京", "两岸", "大陆")


def _gate_pass(text: str) -> bool:
    """确定性门槛：命中领导人信号，或「中国信号 + 亚洲国家/地区信号」。"""
    t = str(text or "")
    if any(k in t for k in _LEADER_HINTS):
        return True
    has_china = any(k in t for k in _CHINA_HINTS)
    has_asia = any(k in t for k in _ASIA_HINTS)
    return has_china and has_asia


_LEVEL_BRACKET_RE = re.compile(r"\[(\d+)\]")
_NEG_WORDS = ("负面", "攻击", "冲突", "批评", "抗议", "丑闻", "辱骂", "暴力")


def _parse_pipe_lines(text: str) -> list[dict]:
    """容错解析竖线分隔的分类输出。

    目标格式（5 字段）：序号|风险等级|情感倾向|关键词1,关键词2|一句话总结
    模型输出格式多变，常见形态：
      [1] 高危 | 负面冲突 | 高墙倒塌事故、死亡、重伤 | 一句话总结
      [0] | 高危 | 冲突/攻击性 | 江泽民, 北京人民大会堂 | 一句话总结
      1|中|负面|关键词1,关键词2
    """
    results: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip().strip("|").strip()
        if not line or line in ("无", "无。", "没有", "none", "None"):
            continue
        # 表头行跳过
        if "序号" in line:
            continue
        # 提取 [N] 序号，其余进入字段解析
        idx = None
        m = _LEVEL_BRACKET_RE.search(line)
        if m:
            idx = int(m.group(1))
            line = (line[:m.start()] + line[m.end():]).strip().strip("|").strip()
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if idx is None:
            try:
                idx = int(parts.pop(0))
            except (TypeError, ValueError, IndexError):
                continue
        # 定位等级字段（容忍 "高危"/"高"/"中风险"/"中高" 等写法）
        li = None
        for i, p in enumerate(parts):
            if _normalize_level(p):
                li = i
                break
        if li is None:
            continue
        level = _normalize_level(parts[li])
        rest = parts[li + 1:]
        # 情感 + 关键词 + 总结：严格模式（3 字段）优先，否则启发式
        sentiment = "中性"
        keywords: list[str] = []
        summary = ""
        if len(rest) >= 3:
            sentiment = rest[0]
            keywords = [k.strip() for k in re.split(r"[,，、;；\s]+", rest[1])]
            summary = rest[2]
        elif len(rest) == 2:
            sentiment = rest[0]
            keywords = [k.strip() for k in re.split(r"[,，、;；\s]+", rest[1])]
        elif len(rest) == 1:
            sentiment = rest[0]
        # 情感归一化
        s = sentiment
        if any(w in s for w in _NEG_WORDS):
            sentiment = "负面"
        elif "正面" in s:
            sentiment = "正面"
        else:
            sentiment = "中性"
        keywords = [k for k in keywords if k and "风险" not in k][:6]
        results.append({
            "index": idx,
            "risk_level": level,
            "sentiment": sentiment,
            "keywords": keywords,
            "summary": summary,
        })
    return results


def _normalize_level(level: str) -> str | None:
    """把模型输出的各种等级写法归一化为 高危/中；低或无法识别返回 None。"""
    level = (level or "").strip()
    if "高" in level:
        return "高危"
    if "中" in level:
        return "中"
    return None


def _parse_time(iso: str | None) -> datetime | None:
    """naive → UTC；带时区 → 原样解析。"""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ_UTC)
    return dt


def _fmt_bj(iso: str | None) -> str:
    dt = _parse_time(iso)
    if dt is None:
        return ""
    return dt.astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")


def _build_post_lines(posts: list[dict]) -> list[tuple[int, str]]:
    """构造带全局序号的贴文行（截取内容控制 token）。"""
    lines = []
    for i, p in enumerate(posts[:_MAX_POSTS]):
        text = _excerpt(str(p.get("title") or "") + " " + str(p.get("content") or ""), _CONTENT_CHARS)
        url = p.get("url") or ""
        tail = (" | 链接: " + url) if url else ""
        lines.append((i, "[" + str(i) + "] " + text + tail))
    return lines


def _chunk_lines(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """按条数与字符数分块。"""
    chunks: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    cur_len = 0
    for item in lines:
        cur.append(item)
        cur_len += len(item[1])
        if len(cur) >= _CHUNK_MAX_POSTS or cur_len >= _CHUNK_MAX_CHARS:
            chunks.append(cur)
            cur, cur_len = [], 0
    if cur:
        chunks.append(cur)
    return chunks


async def _classify_chunk(chunk_lines: list[tuple[int, str]]) -> list[dict]:
    """分类一个块，返回 [{index, risk_level, sentiment, keywords}]。失败返回空列表。"""
    chunk_prompt = "\n".join(l for _, l in chunk_lines)
    for _attempt in range(2):
        try:
            raw = await summarizer._call_ai(RISK_SYSTEM_PROMPT, chunk_prompt, max_tokens=16384)
            if (raw or "").strip() in ("无", "无。", "没有", "none", "None"):
                return []  # 模型明确判定本块无中高风险贴文，不重试
            parsed = _parse_pipe_lines(raw)
            if parsed:
                return parsed
            logger.warning("[risk] 分类块无有效输出，重试: %s", raw[:120])
        except Exception as e:
            logger.warning("[risk] 分类块失败，重试: %s", str(e)[:120])
    return []


async def _summarize_important(important: list[dict]) -> str:
    """对筛出的重要贴文生成总摘要。失败返回提示文本。"""
    lines = []
    for i, p in enumerate(important):
        text = _excerpt(str(p["title"]) + " " + str(p["summary"]), 300)
        lines.append(str(i + 1) + ". " + text)
    user_prompt = "\n".join(lines)
    for _attempt in range(2):
        try:
            raw = await summarizer._call_ai(SUMMARY_SYSTEM_PROMPT, user_prompt, max_tokens=16384)
            raw = _truncate_summary(raw)
            if len(raw) >= 20:
                return raw
            logger.warning("[risk] 总摘要过短，重试: %s", raw[:100])
        except Exception as e:
            logger.warning("[risk] 总摘要失败，重试: %s", str(e)[:120])
    return "（AI 摘要生成失败，请查看下方贴文）"


async def analyze_monitor_posts(
    posts: list[dict], platform: str, account_name: str
) -> tuple[list[dict], str] | None:
    """分段风险分类 + 汇总。

    返回 (important_posts, ai_summary)；失败或无中高风险贴文时返回 None
    （调用方降级为旧格式推送）。
    """
    if not posts:
        return None
    try:
        # ── 阶段一：分块分类 ──
        classified: dict[int, dict] = {}
        for chunk in _chunk_lines(_build_post_lines(posts)):
            for ap in await _classify_chunk(chunk):
                try:
                    idx = int(ap.get("index", -1))
                except (TypeError, ValueError):
                    continue
                level = _normalize_level(str(ap.get("risk_level") or ""))
                if level is None or not (0 <= idx < len(posts)):
                    continue
                # 同一条贴文被多块重复分类时取风险更高者
                old = classified.get(idx)
                if old is None or (level == "高危" and old["risk_level"] != "高危"):
                    classified[idx] = {
                        "risk_level": level,
                        "sentiment": str(ap.get("sentiment") or "中性"),
                        "keywords": [str(k) for k in (ap.get("keywords") or []) if str(k).strip()],
                        "summary": str(ap.get("summary") or "").strip(),
                    }

        if not classified:
            logger.info("[risk] 分块分类完成: 无中高风险贴文 (%s 条输入)", len(posts))
            return None

        # ── 组装重要贴文（内容字段全部取自原帖，保证一一对应） ──
        important: list[dict] = []
        for idx, cls in classified.items():
            src = posts[idx]
            content = _excerpt(src.get("content") or "", 300)
            title0 = _excerpt(src.get("title") or "", 80) or content[:80]
            if not _gate_pass(title0 + " " + content):
                continue  # 未命中硬规则（领导人 / 中国+亚洲负面），丢弃
            cls["title0"] = title0
            cls["content"] = content
            ai_post_summary = cls.get("summary") or ""
            post_summary = _truncate_summary(ai_post_summary, 100) if ai_post_summary else cls["content"][:100]
            important.append({
                "risk_level": cls["risk_level"],
                "title": cls["title0"],
                "url": src.get("url") or "",
                "summary": post_summary,
                "published_at": src.get("published_at"),
                "author_name": src.get("author_name") or "",
                "sentiment": cls["sentiment"],
                "keywords": cls["keywords"],
            })

        if not important:
            logger.info("[risk] 候选贴文均未命中硬规则（领导人/中国+亚洲负面），不推送 (%s 条输入)", len(posts))
            return None

        def _sort_key(p: dict):
            lvl = 0 if p["risk_level"] == "高危" else 1
            t = _parse_time(p.get("published_at"))
            return (lvl, -(t.timestamp() if t else 0))
        important.sort(key=_sort_key)
        important = important[:10]

        # ── 阶段二：汇总摘要 ──
        summary = await _summarize_important(important)
        logger.info("[risk] 风险分析完成: %s 条输入, %s 块, %s 条中高风险",
                    len(posts), len(_chunk_lines(_build_post_lines(posts))), len(important))
        return important, summary
    except Exception as e:
        logger.exception("[risk] 风险分析失败: %s", e)
        return None


_CN_NUMS = "一二三四五六七八九十"


def _derive_range(posts: list[dict]) -> str:
    """从贴文列表推导时间跨度标签（北京时间）。"""
    times = sorted(
        t for t in (_parse_time(p.get("published_at")) for p in posts) if t is not None
    )
    if not times:
        return "未知"
    return (
        times[0].astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")
        + " ~ "
        + times[-1].astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")
        + "（北京时间）"
    )


def _cn_num(n: int) -> str:
    if 1 <= n <= 10:
        return _CN_NUMS[n - 1]
    if 11 <= n <= 19:
        return "十" + _CN_NUMS[n - 11]
    return str(n)


def time_range_label(time_start=None, time_end=None, posts: list[dict] | None = None) -> str:
    """任务筛选时间范围标签（北京时间）。

    - 有任务窗口（立即执行传入 start/end）→ 直接展示任务窗口；
    - 无窗口（定时任务）→ 用全部抓取贴文的实际时间跨度；
    - 都没有 → 未知。
    """
    if time_start or time_end:
        if time_start and time_end:
            return (_fmt_bj(time_start) + " ~ " + _fmt_bj(time_end) + "（北京时间）")
        if time_start:
            return _fmt_bj(time_start) + " 起（北京时间）"
        return "截至 " + _fmt_bj(time_end) + "（北京时间）"
    if posts:
        times = sorted(
            t for t in (_parse_time(p.get("published_at")) for p in posts) if t is not None
        )
        if times:
            return (
                times[0].astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")
                + " ~ "
                + times[-1].astimezone(TZ_SHANGHAI).strftime("%Y-%m-%d %H:%M")
                + "（北京时间）"
            )
    return "未知"


def format_important_markdown(
    important: list[dict],
    ai_summary: str,
    platform: str,
    account_name: str,
    total_posts: int | None = None,
    time_range_label: str | None = None,
) -> str:
    """按推送案例格式生成 markdown 正文。

    total_posts / time_range_label 反映「任务筛选范围内的总量」，
    未提供时回退为重要贴文的数量与时间跨度。
    """
    trange = time_range_label if time_range_label else _derive_range(important)
    count = total_posts if total_posts is not None else len(important)

    source = PLATFORM_LABELS.get(platform, platform)
    out = [
        "**发帖时间范围**：" + trange,
        "**发帖数量**：" + str(count),
        "",
        "**AI摘要**：",
        ai_summary,
        "",
        "**重要贴文如下**：",
        "",
    ]
    for i, p in enumerate(important, 1):
        out.append("**" + _cn_num(i) + "、**")
        out.append("**风险等级**：" + p["risk_level"])
        out.append("**标题**：" + (p["title"] or "（无标题）"))
        if p["url"]:
            out.append("**链接**：" + p["url"])
        out.append("**摘要**：" + (p["summary"] or "（无）"))
        out.append("**时间**：" + (_fmt_bj(p.get("published_at")) or "未知"))
        out.append("**来源**：" + source)
        author = p.get("author_name") or account_name
        out.append("**作者**：" + (author or "-"))
        out.append("**情感倾向**：" + p["sentiment"])
        out.append("**提及关键词**：" + (" ".join(p["keywords"]) if p["keywords"] else "-"))
        out.append("")
    return "\n".join(out).rstrip()

