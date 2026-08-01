# intel-monitor/backend/crawlers/telegram/parser.py
"""
Telegram @kuai search result parser.

Pure functions: consume HTML/element data, produce PostData.
No browser interaction here — see bot.py for Playwright DOM operations.
"""
import logging
from datetime import datetime

from crawlers.base import PostData

logger = logging.getLogger(__name__)

# ── @kuai Bot reply parsing ──────────────────────────────────────────────────

# Result items in the Bot reply use these content-type prefixes:
CONTENT_TYPE_ICONS = {
    "\U0001f3de": "image",   # 🏞
    "\U0001f3ac": "video",   # 🎬
    "\U0001f4c4": "document",  # 📄
}

# Skip items whose title starts with these markers
AD_SIGNAL = "广告"  # 广告


def is_ad_result(title: str) -> bool:
    """Return True if the result item is an advertisement."""
    return title.strip().startswith(AD_SIGNAL) or AD_SIGNAL in title[:6]


def parse_result_item_link(title: str) -> str | None:
    """Extract the t.me link from a result item title string.

    The Bot reply embeds links as clickable text; the underlying URL
    is extracted by the bot layer via DOM attributes.  This helper
    is a fallback that regex-matches t.me/XXXXX/NNN patterns from
    plain text when the DOM link is unavailable.
    """
    import re
    m = re.search(r't\.me/([a-zA-Z0-9_]+)/(\d+)', title)
    if m:
        return f"https://t.me/{m.group(1)}/{m.group(2)}"
    return None


# ── Channel message parsing ──────────────────────────────────────────────────


def parse_channel_message(page_text: str, page_url: str) -> PostData:
    """Parse a Telegram channel message page into PostData.

    Args:
        page_text: Full innerText of the message viewport.
        page_url: Current page URL (e.g. https://t.me/gy0hxsoqt4xd/13214).

    Returns:
        PostData with title (first meaningful line), content (rest),
        and url set to page_url.
    """
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    # Skip noise lines
    skip_prefixes = (
        "没看够？", "加入隐私群组", "点击加入", "广告",  # 广告
        "赞助商", "SUBSCRIBE", "Broadcast", "Message",
    )
    clean = []
    for l in lines:
        low = l.lower()
        if low.startswith(tuple(s.lower() for s in skip_prefixes if s.isascii())) or \
           l.startswith(tuple(s for s in skip_prefixes if not s.isascii())):
            continue
        # Skip Telegram UI chrome
        if l in ("", "", "", "", "", "", ""):
            continue
        clean.append(l)

    if not clean:
        return PostData(url=page_url, title="", content="")

    # First meaningful line is the title
    title = clean[0] if clean else ""
    # Rest is content
    content = "\n".join(clean[1:]) if len(clean) > 1 else ""

    # Extract tags from content (prefixed with #)
    tags = []
    import re
    tags = re.findall(r'#[^\s#]+', content)

    return PostData(
        url=page_url,
        title=title[:200],
        content=content[:5000] if content else title[:200],
    )


def parse_subscriber_count(text: str) -> int:
    """Parse subscriber count from channel header text like '33 subscribers'.

    Also handles '1 234 subscribers', '1.2K subscribers', etc.
    """
    import re

    text = text.strip().replace(" ", " ").replace(",", "")
    # "1.2K subscribers" pattern
    m = re.search(r'([\d.]+)\s*K?\s*subscribers?', text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        if 'k' in text.lower():
            val *= 1000
        return int(val)
    return 0


def parse_message_timestamp(text: str) -> datetime | None:
    """Parse Telegram message timestamp into naive UTC datetime.

    Telegram Web displays timestamps relative ("May 18") or absolute ("14:38").
    For channel messages, we expect formats like:
      - "May 18" (date only, assume current year)
      - "May 18, 2024" (full date)
      - "14:38" (time only, assume today)
    """
    from datetime import datetime, timezone, timedelta
    from crawlers.base import parse_absolute_time

    text = text.strip()

    # Try standard absolute parsing first
    dt = parse_absolute_time(text, assume_utc=True)
    if dt:
        return dt

    # Try "Month Day" format (e.g. "May 18")
    import re
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    m = re.match(r'([A-Z][a-z]+)\s+(\d{1,2})', text)
    if m:
        month = month_map.get(m.group(1).lower())
        day = int(m.group(2))
        if month:
            now = datetime.now(timezone.utc)
            return datetime(now.year, month, day, tzinfo=timezone.utc).replace(tzinfo=None)

    return None
