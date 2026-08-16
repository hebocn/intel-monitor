# intel-monitor/backend/services/report_writer.py
"""DeepSeek 三阶段 AI 流水线：事实提取 → 逐章撰写 → 统稿润色。"""

import json
import logging
from datetime import datetime
import httpx
from config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

MAX_CHARS_PER_BATCH = 25000  # ~6000 tokens per batch, safe for DeepSeek context
MAX_SOURCES_PER_BATCH = 5  # 小上下文模型友好；输出截断时还会自动对半拆分重试
MAX_SOURCE_CHARS = 1500  # 单条来源内容截断上限（15 条×3000 字符对 flash 类模型过大）

# ── System prompts ─────────────────────────────────────────────────────────

STAGE1_SYSTEM = settings.INTELLIGENCE_REPORT_PROMPT + (
    "\n\n当前任务：事实提取阶段。\n"
    "从以下开源情报素材中提取关键事实、数据点和关联关系。\n\n"
    "输出要求（返回严格的 JSON 格式）：\n"
    "```json\n"
    "{\n"
    '  "facts": [\n'
    '    {"text": "事实描述（简洁，一句话）", "source_url": "来源URL", "source_title": "来源标题", "category": "分类（组织/物品/传播/安全/政策/其他）"},\n'
    '    ...\n'
    '  ],\n'
    '  "data_points": [\n'
    '    {"metric": "指标名（如信徒规模/年增长率/销售额等）", "value": "数值", "unit": "单位", "source_url": "来源URL"},\n'
    '    ...\n'
    '  ],\n'
    '  "relationships": [\n'
    '    {"subject": "主体A", "relation": "关系描述", "object": "主体B", "significance": "情报意义（简短）"},\n'
    '    ...\n'
    '  ]\n'
    "}\n"
    "```\n"
    "只输出 JSON，不要输出任何其他内容。确保 JSON 有效可解析。"
)

STAGE2_SECTION_SYSTEM = settings.INTELLIGENCE_REPORT_PROMPT + (
    "\n\n当前任务：逐章撰写阶段。\n"
    "基于提取的事实清单，撰写情报报告的一个章节。\n\n"
    "写作要求：\n"
    "1. 使用规范严谨的公安情报语言，语气专业、客观、冷静\n"
    "2. 每个论点必须有事实支撑，引用具体来源作为脚注\n"
    "3. 深度研判，不做表面描述——分析背后的动因、趋势、风险\n"
    "4. 使用 Markdown 格式输出，包含二级/三级标题、列表、加粗重点\n"
    "5. 本章控制在 800-2000 字\n"
    "6. 输出纯 Markdown 内容，不要输出其他说明"
)

STAGE3_SYSTEM = ""  # computed dynamically

QUERY_SPLIT_SYSTEM = (
    "你是一位精通公安情报业务的搜索策略专家。"
    "用户输入一个情报研究主题，你需要将其拆分为多条精准的搜索查询，"
    "确保通过搜索引擎能够覆盖该主题的所有关键维度。\n\n"
    "拆分原则：\n"
    "1. 每条查询应该简短精确（10-25字），适合搜索引擎\n"
    "2. 覆盖不同角度：事件本身、参与者/组织、相关物品/产品、法律法规、历史背景、近期动态等\n"
    "3. 部分查询应包含具体平台名（如\"淘宝 宗教用品\"）以定向搜索\n"
    "4. 部分查询应包含\"风险\"\"安全\"\"管控\"等公安情报关键词\n"
    "5. 输出 8-15 条查询\n\n"
    "返回纯 JSON 数组，每条为 {query, dimension}，dimension 说明该查询覆盖的维度。"
    "只输出 JSON 数组，不要其他内容。"
)

CONTENT_FILTER_SYSTEM = (
    "你是一位情报分析师，需要从一批搜索结果中筛选出与给定主题高度相关的条目。\n\n"
    "对每条结果，判断其相关度：\n"
    "- high: 直接相关，包含大量有价值信息\n"
    "- medium: 部分相关，可作为背景参考\n"
    "- low: 基本不相关或质量太差\n\n"
    "返回 JSON 数组：[{\"index\": 0, \"relevance\": \"high|medium|low\", \"reason\": \"一句话理由\"}, ...]\n"
    "只输出 JSON 数组，不要其他内容。"
)

# ── AI call helper ──────────────────────────────────────────────────────────

async def _call_deepseek(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    timeout: int = 120,
    max_tokens: int = 8192,
) -> tuple[str, bool]:
    """Call DeepSeek API (OpenAI compatible). Returns (content, truncated).

    truncated=True 表示输出因达到 max_tokens 被截断（finish_reason=length），
    调用方应据此降级（如回退草稿），避免把不完整内容当完整结果。
    """
    if not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
    api_url = f"{base_url}/chat/completions"
    model = settings.DEEPSEEK_MODEL or "deepseek-chat"

    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        # 关闭思考模式：报告流水线全是结构化任务，推理 token 会挤占
        # max_tokens 输出预算（deepseek-v4-flash 曾因推理过长导致输出截断、
        # JSON 解析失败、事实提取批次被静默丢弃）
        "thinking": {"type": "disabled"},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(api_url, headers=headers, json=payload)
        if resp.status_code == 400 and "thinking" in (resp.text or "").lower():
            # 端点/模型不支持 thinking 参数（如旧版或兼容层），去掉后重试
            payload.pop("thinking", None)
            resp = await client.post(api_url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        err = data.get("error")
        if err:
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise RuntimeError(f"DeepSeek API error: {msg}")

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("DeepSeek returned no choices")
        content = choices[0]["message"]["content"]
        finish_reason = choices[0].get("finish_reason")
        truncated = finish_reason == "length"
        if truncated:
            logger.warning(f"DeepSeek output truncated (finish_reason=length), got {len(content)} chars")
        return content, truncated


def _safe_json_extract(text: str) -> str:
    """Extract JSON from model output that may contain markdown code fences."""
    text = text.strip()
    # Remove ```json ... ``` fences
    if text.startswith("```"):
        idx = text.find("\n")
        if idx > 0:
            text = text[idx + 1:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


# ── Phase helpers ───────────────────────────────────────────────────────────

async def split_query(topic: str) -> list[dict]:
    """Phase 1: Split user topic into multiple search queries."""
    result, _ = await _call_deepseek(QUERY_SPLIT_SYSTEM, f"情报研究主题：\n{topic}", temperature=0.3, timeout=60)
    try:
        queries = json.loads(_safe_json_extract(result))
        if isinstance(queries, list) and len(queries) > 0:
            return queries
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Query split JSON parse failed: {e}, raw: {result[:200]}")
    # Fallback: use topic directly
    return [{"query": topic[:100], "dimension": "主搜索"}]


async def filter_sources(topic: str, sources: list[dict]) -> list[dict]:
    """Phase 3: AI filters sources by relevance to topic."""
    if len(sources) <= 20:
        # Small enough, just return with high relevance
        for s in sources:
            s["relevance"] = "medium"
            s["relevance_reason"] = "批量保留"
        return sources

    # Batch filter to avoid exceeding DeepSeek context window
    FILTER_BATCH_SIZE = 20  # ~20 sources per batch keeps text manageable (小上下文模型友好)
    all_filtered = []

    for batch_start in range(0, len(sources), FILTER_BATCH_SIZE):
        batch = sources[batch_start:batch_start + FILTER_BATCH_SIZE]

        # Build index text for filtering
        entries = []
        for i, s in enumerate(batch):
            text = s.get("markdown", s.get("content", ""))[:500]
            entries.append(
                f"[{i}] title: {s.get('title','')[:100]}\n"
                f"    desc: {s.get('description','')[:150]}\n"
                f"    preview: {text[:200]}"
            )
        candidates_text = "\n\n".join(entries)

        try:
            result, _ = await _call_deepseek(CONTENT_FILTER_SYSTEM, f"研究主题：\n{topic}\n\n候选材料：\n{candidates_text}", temperature=0.3, timeout=90)
            ratings = json.loads(_safe_json_extract(result))
            rating_map = {r["index"]: r for r in ratings if isinstance(r, dict) and "index" in r}
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Filter batch {batch_start//FILTER_BATCH_SIZE + 1} failed: {e}, keeping all as medium")
            rating_map = {}

        for i, s in enumerate(batch):
            rating = rating_map.get(i, {})
            relevance = rating.get("relevance", "medium")
            s["relevance"] = relevance
            s["relevance_reason"] = rating.get("reason", "")
            if relevance in ("high", "medium"):
                all_filtered.append(s)

    logger.info(f"Filter completed: {len(sources)} → {len(all_filtered)} (filtered out {len(sources) - len(all_filtered)})")
    return all_filtered


# ── Stage 1: Facts Extraction ──────────────────────────────────────────────

async def _extract_facts_batch(offset: int, batch: list[dict], depth: int = 0) -> tuple[list, list, list]:
    """Extract facts from one batch; recursively split in half when output is truncated."""
    batch_text_parts = []
    for i, s in enumerate(batch):
        md = (s.get("markdown") or s.get("content") or "")[:MAX_SOURCE_CHARS]
        batch_text_parts.append(
            f"### 来源 [{offset + i}]\n"
            f"标题: {s.get('title', '无')}\n"
            f"URL: {s.get('url', '')}\n"
            f"内容:\n{md}"
        )
    batch_text = "\n\n".join(batch_text_parts)

    if len(batch_text) > MAX_CHARS_PER_BATCH:
        batch_text = batch_text[:MAX_CHARS_PER_BATCH]

    logger.info(f"Stage 1 batch [{offset}:{offset + len(batch)}]: {len(batch)} sources, {len(batch_text)} chars, depth={depth}")

    try:
        result, truncated = await _call_deepseek(STAGE1_SYSTEM, batch_text, temperature=0.3, timeout=180)
    except Exception as e:
        logger.warning(f"Stage 1 batch [{offset}] API call failed: {e}")
        return [], [], []

    if truncated and len(batch) > 1 and depth < 3:
        mid = len(batch) // 2
        logger.warning(f"Stage 1 batch [{offset}] output truncated, splitting {len(batch)} -> {mid} + {len(batch) - mid}")
        a = await _extract_facts_batch(offset, batch[:mid], depth + 1)
        b = await _extract_facts_batch(offset + mid, batch[mid:], depth + 1)
        return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

    try:
        parsed = json.loads(_safe_json_extract(result))
        return (
            parsed.get("facts", []),
            parsed.get("data_points", []),
            parsed.get("relationships", []),
        )
    except Exception as e:
        logger.warning(f"Stage 1 batch [{offset}] JSON parse failed (truncated={truncated}): {e}")
        return [], [], []


async def stage1_extract_facts(sources: list[dict]) -> dict:
    """Extract structured facts, data points, and relationships from all sources."""
    if not sources:
        return {"facts": [], "data_points": [], "relationships": []}

    all_facts = []
    all_data_points = []
    all_relationships = []

    # Batch sources to fit context; truncated batches are split and retried
    for batch_start in range(0, len(sources), MAX_SOURCES_PER_BATCH):
        batch = sources[batch_start:batch_start + MAX_SOURCES_PER_BATCH]
        facts, data_points, relationships = await _extract_facts_batch(batch_start, batch)
        all_facts.extend(facts)
        all_data_points.extend(data_points)
        all_relationships.extend(relationships)

    # Deduplicate facts (by text similarity — simple prefix match)
    seen_texts = set()
    deduped_facts = []
    for f in all_facts:
        key = f.get("text", "")[:60]
        if key not in seen_texts and len(f.get("text", "")) > 5:
            seen_texts.add(key)
            deduped_facts.append(f)

    result = {
        "facts": deduped_facts,
        "data_points": all_data_points,
        "relationships": all_relationships,
    }
    logger.info(f"Stage 1 completed: {len(deduped_facts)} facts, {len(all_data_points)} data points, {len(all_relationships)} relationships")
    return result


# ── Stage 2: Section Writing ───────────────────────────────────────────────

async def stage2_write_sections(facts_data: dict, topic: str) -> str:
    """AI determines chapter structure and writes each section."""
    if not facts_data.get("facts") and not facts_data.get("data_points"):
        return "# 情报报告\n\n无足够素材生成有效报告。请扩大搜索范围或调整主题。"

    # Build facts summary
    facts_text = json.dumps(facts_data, ensure_ascii=False, indent=2)

    # First, let AI plan the chapter structure
    chapter_prompt = (
        "基于以下事实清单，为情报报告规划章节结构。\n"
        "必须包含以下章节（至少）：\n"
        "1. 一、主旨相关基本信息\n"
        "2. 二、风险隐患综合分析\n"
        "3. 三、对策建议\n"
        "其余章节可根据事实自由组织，结构要合理、专业。\n\n"
        "返回 JSON：{\"chapters\": [{\"title\": \"章标题\", \"brief\": \"本章要点（30字）\"}, ...]}\n"
        "只输出 JSON，不要其他内容。"
    )

    chapters_json = ""
    try:
        result, _ = await _call_deepseek(STAGE2_SECTION_SYSTEM, chapter_prompt + f"\n\n主题：{topic}\n\n事实清单：\n{facts_text[:12000]}", temperature=0.5, timeout=90)
        parsed = json.loads(_safe_json_extract(result))
        chapters = parsed.get("chapters", [])
    except Exception:
        chapters = [
            {"title": "一、主旨相关基本信息", "brief": ""},
            {"title": "二、风险隐患综合分析", "brief": ""},
            {"title": "三、对策建议", "brief": ""},
        ]

    if not chapters:
        chapters = [
            {"title": "一、主旨相关基本信息", "brief": ""},
            {"title": "二、风险隐患综合分析", "brief": ""},
            {"title": "三、对策建议", "brief": ""},
        ]

    logger.info(f"Stage 2 chapters: {[c['title'] for c in chapters]}")

    # Write each chapter
    sections = []
    for ch in chapters:
        ch_prompt = (
            f"请撰写以下章节：\n"
            f"章节标题：{ch['title']}\n"
            f"本章要点：{ch.get('brief', '')}\n\n"
            f"可引用的基础事实：\n{facts_text[:12000]}\n\n"
            f"研究主题：{topic}"
        )
        try:
            content, truncated = await _call_deepseek(
                STAGE2_SECTION_SYSTEM, ch_prompt, temperature=0.6, timeout=180, max_tokens=8192,
            )
            if truncated:
                logger.warning(f"Stage 2 chapter '{ch["title"]}' truncated at {len(content)} chars")
            sections.append({"title": ch["title"], "content": content.strip()})
            logger.info(f"Stage 2 wrote chapter: {ch['title']} ({len(content)} chars, truncated={truncated})")
        except Exception as e:
            logger.error(f"Stage 2 failed on chapter {ch['title']}: {e}")
            sections.append({"title": ch["title"], "content": f"## {ch['title']}\n\n本章撰写失败: {e}"})

    # Assemble full draft
    full_draft = f"# 战略情报报告\n\n**主题：{topic}**\n\n---\n\n"
    for sec in sections:
        full_draft += sec["content"] + "\n\n---\n\n"

    return full_draft


# ── Stage 3: Polishing ─────────────────────────────────────────────────────

async def stage3_polish(draft: str, topic: str) -> str:
    """Final review, consistency check, language polishing."""
    logger.info("Stage 3: polishing final report")
    today = datetime.now().strftime("%Y年%m月%d日")
    stage3_system = settings.INTELLIGENCE_REPORT_PROMPT + (
        "\n\n当前任务：统稿润色阶段。\n"
        "对以下完整的报告草稿进行全书统稿。\n\n"
        "统稿要求：\n"
        "1. 消除章节间重复内容，合并同类论述\n"
        "2. 统一术语表述，确保全文用词一致\n"
        "3. 确保逻辑递进流畅，章节之间衔接自然\n"
        "4. 修正可能的语法错误和表述不当\n"
        "5. 保留所有 Markdown 格式和脚注引用\n"
        f"6. 在报告标题下方添加「编制单位：情报监测平台」和「报告日期：{today}」的副标题信息\n"
        "7. 输出完整的 Markdown 全文（不要截断），不要输出其他说明"
    )
    try:
        polished, truncated = await _call_deepseek(
            stage3_system,
            f"研究主题：{topic}\n\n报告草稿：\n{draft}",
            temperature=0.4,
            timeout=180,
            max_tokens=16384,
        )
        if truncated:
            logger.warning(f"Stage 3 output truncated ({len(polished)} chars), falling back to unpolished draft")
        elif polished and len(polished.strip()) > 500:
            if len(polished.strip()) < len(draft) * 0.5:
                logger.warning(f"Stage 3 output suspiciously short ({len(polished)} vs draft {len(draft)}), using draft")
            else:
                logger.info(f"Stage 3 completed: {len(polished)} chars")
                return polished.strip()
    except Exception as e:
        logger.error(f"Stage 3 failed: {e}")

    # Fallback: return draft as-is
    logger.warning("Stage 3 fallback: returning unpolished draft")
    return draft


# ── Main pipeline ───────────────────────────────────────────────────────────

async def run_report_writer(topic: str, sources: list[dict]) -> str:
    """Execute the full three-stage AI pipeline and return final markdown report."""
    if not sources:
        return (
            "# 战略情报报告\n\n"
            "## 生成状态\n\n"
            "搜索未获取到有效素材。请检查以下方面：\n"
            "1. 主题描述是否足够明确具体\n"
            "2. 搜索覆盖的平台和引擎是否合理\n"
            "3. 建议调整搜索参数后重新生成\n\n"
            f"**原始主题：**{topic}"
        )

    logger.info(f"Report writer starting: {len(sources)} sources, topic='{topic[:60]}...'")

    # Stage 1: Facts extraction
    facts = await stage1_extract_facts(sources)
    if not facts.get("facts") and not facts.get("data_points"):
        logger.warning("No facts extracted from sources")

    # Stage 2: Chapter writing
    draft = await stage2_write_sections(facts, topic)

    # Stage 3: Polish
    final = await stage3_polish(draft, topic)

    return final
