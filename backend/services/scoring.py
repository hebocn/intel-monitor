# intel-monitor/backend/services/scoring.py
import logging
from math import log10, log, exp
from datetime import datetime, timezone

from sqlalchemy import select, func
from database import async_session
from models.platform_stats import PlatformStats
from models.sentiment_post import SentimentPost

logger = logging.getLogger(__name__)

INTERACTION_WEIGHTS = {
    "views": 0.5,
    "likes": 1.0,
    "comments": 2.5,
    "shares": 3.5,
    "bookmarks": 2.0,
}

METRICS = ["views", "likes", "comments", "shares", "bookmarks"]

PLATFORM_MAU_DEFAULTS = {
    "weibo": 586_000_000,
    "douyin": 730_000_000,
    "xiaohongshu": 300_000_000,
    "toutiao": 350_000_000,
    "108community": 500_000,
    "youtube": 2_500_000_000,
    "x": 500_000_000,
    "facebook": 600_000_000,
    "telegram_kuai": 900_000_000,
}

DEFAULT_HALF_LIFE_DAYS = 4.0


def _interpolate_percentile(value: float, stats: PlatformStats) -> float:
    """Linear interpolate value between known percentiles."""
    thresholds = [
        (0.50, stats.p50),
        (0.75, stats.p75),
        (0.90, stats.p90),
        (0.95, stats.p95),
        (0.99, stats.p99),
    ]
    if value <= thresholds[0][1]:
        return 0.50 * (value / max(thresholds[0][1], 1))
    for i in range(len(thresholds) - 1):
        p_lo, v_lo = thresholds[i]
        p_hi, v_hi = thresholds[i + 1]
        if v_lo <= value <= v_hi:
            if v_hi == v_lo:
                return p_lo
            frac = (value - v_lo) / (v_hi - v_lo)
            return p_lo + frac * (p_hi - p_lo)
    # Beyond p99
    if thresholds[-1][1] > 0:
        extra = (value - thresholds[-1][1]) / thresholds[-1][1]
        return min(1.0, 0.99 + extra * 0.01)
    return 0.99


def _log10_score(value: float, all_values: list[float]) -> float:
    """log10 normalization: log10(v+1) / log10(max+1)."""
    max_val = max(all_values) if all_values else 1
    if max_val <= 0:
        return 0.0
    return log10(value + 1) / log10(max_val + 1)


def calculate_impact(
    post: SentimentPost,
    stats_dict: dict[tuple[str, str], PlatformStats],
    platform_mau: dict[str, int],
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    all_platform_values: dict[tuple[str, str], list[float]] | None = None,
) -> dict:
    """Calculate influence score for a single post."""
    scores = {}
    available_weights = {}

    for metric in METRICS:
        v = getattr(post, metric, 0)
        key = (post.platform, metric)
        stats = stats_dict.get(key)

        if stats and stats.sample_count >= 1000:
            p = _interpolate_percentile(v, stats)
        elif all_platform_values and key in all_platform_values:
            p = _log10_score(v, all_platform_values[key])
        elif v > 0:
            # Cold start: use self-referencing log10 score
            # Fallback so new platforms don't get zero scores
            p = log10(v + 1) / log10(v + 2)  # asymptotic to ~1.0 for large v
        else:
            p = 0.0

        scores[metric] = p
        if not post.metrics_partial or v > 0:
            available_weights[metric] = INTERACTION_WEIGHTS[metric]

    if not post.metrics_partial:
        available_weights = dict(INTERACTION_WEIGHTS)

    denominator = sum(available_weights.values()) or 1.0
    numerator = sum(scores[m] * available_weights.get(m, 0) for m in scores)
    engagement = numerator / denominator

    mau = platform_mau.get(post.platform, 1_000_000)
    max_mau = max(platform_mau.values()) if platform_mau else 1_000_000_000
    if max_mau > 0 and mau > 0:
        raw_weight = log10(mau) / log10(max_mau)
    else:
        raw_weight = 0.5
    platform_weight = max(0.3, min(0.7, raw_weight))

    days = 7.0  # default penalty for posts without published_at
    if post.published_at:
        delta = datetime.now(timezone.utc).replace(tzinfo=None) - post.published_at
        days = max(0, delta.total_seconds() / 86400)
    lam = log(2) / half_life_days if half_life_days > 0 else 0
    time_decay = exp(-lam * days)

    impact_score = engagement * platform_weight * time_decay * 100

    import json
    return {
        "engagement_score": round(engagement, 4),
        "platform_weight": round(platform_weight, 4),
        "time_decay": round(time_decay, 4),
        "impact_score": round(impact_score, 2),
        "score_detail": json.dumps({m: round(s, 4) for m, s in scores.items()}, ensure_ascii=False),
    }


async def refresh_platform_stats():
    """Recalculate PlatformStats from all SentimentPost data."""
    async with async_session() as db:
        for platform in PLATFORM_MAU_DEFAULTS:
            for metric in METRICS:
                col = getattr(SentimentPost, metric)
                stmt = (
                    select(col)
                    .where(SentimentPost.platform == platform)
                )
                result = await db.execute(stmt)
                values = sorted([r[0] for r in result.fetchall() if r[0] is not None and r[0] > 0])

                if not values:
                    continue

                n = len(values)

                def _pct(pct_val):
                    idx = int(n * pct_val)
                    return float(values[min(idx, n - 1)])

                existing = await db.execute(
                    select(PlatformStats).where(
                        PlatformStats.platform == platform,
                        PlatformStats.metric == metric,
                    )
                )
                stats = existing.scalar_one_or_none()

                if stats:
                    stats.p50 = _pct(0.50)
                    stats.p75 = _pct(0.75)
                    stats.p90 = _pct(0.90)
                    stats.p95 = _pct(0.95)
                    stats.p99 = _pct(0.99)
                    stats.sample_count = n
                else:
                    stats = PlatformStats(
                        platform=platform,
                        metric=metric,
                        p50=_pct(0.50),
                        p75=_pct(0.75),
                        p90=_pct(0.90),
                        p95=_pct(0.95),
                        p99=_pct(0.99),
                        sample_count=n,
                    )
                    db.add(stats)

        await db.commit()
    logger.info("PlatformStats refreshed")


async def get_platform_stats_dict(db) -> dict[tuple[str, str], PlatformStats]:
    """Load all PlatformStats into a lookup dict."""
    result = await db.execute(select(PlatformStats))
    stats_dict = {}
    for s in result.scalars().all():
        stats_dict[(s.platform, s.metric)] = s
    return stats_dict


async def get_platform_all_values(db) -> dict[tuple[str, str], list[float]]:
    """Load all metric values grouped by (platform, metric) for cold-start log10."""
    values_dict: dict[tuple[str, str], list[float]] = {}
    for platform in PLATFORM_MAU_DEFAULTS:
        for metric in METRICS:
            col = getattr(SentimentPost, metric)
            result = await db.execute(
                select(col).where(SentimentPost.platform == platform)
            )
            vals = [r[0] for r in result.fetchall() if r[0] is not None and r[0] > 0]
            if vals:
                values_dict[(platform, metric)] = vals
    return values_dict
