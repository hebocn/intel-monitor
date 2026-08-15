# intel-monitor/backend/services/weather.py
"""台风/极端天气数据服务（数据源：中央气象台 NMC）。

- 抓取 typhoon.nmc.cn 台风列表/轨迹 + weather.com.cn 当前生效预警
- 内存 TTL 缓存 10 分钟，惰性抓取
- 抓取成功时 upsert 轨迹点到 typhoon_tracks 表顺带存档
- 接口失败时优雅降级：返回 degraded=True + 上次成功快照（若有）
- 时间处理：源数据为北京时间，统一转 naive UTC（项目红线）
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database import async_session
from models.typhoon import TyphoonTrack

logger = logging.getLogger(__name__)

# ── NMC 接口 ──
TYPHOON_LIST_URL = "https://typhoon.nmc.cn/weatherservice/typhoon/jsons/list_default"
TYPHOON_VIEW_URL = "https://typhoon.nmc.cn/weatherservice/typhoon/jsons/view_{id}"
WARNINGS_URL = "http://product.weather.com.cn/alarm/grepalarm_cn.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "http://typhoon.nmc.cn/",
}

CACHE_TTL_SECONDS = 600
MAX_WARNINGS = 300          # 预警打点上限（全量 900+ 时避免地图过载）
BEIJING_OFFSET = timedelta(hours=8)

LEVEL_LABELS = {
    "TD": "热带低压", "TS": "热带风暴", "STS": "强热带风暴",
    "TY": "台风", "STY": "强台风", "SuperTY": "超强台风",
}
WARNING_LEVEL_CODES = {"蓝色": "blue", "黄色": "yellow", "橙色": "orange", "红色": "red"}

_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}


# ── 缓存 ──

def _cache_get(key: str):
    item = _cache.get(key)
    if item and time.monotonic() - item[0] < CACHE_TTL_SECONDS:
        return item[1]
    return None


def _cache_set(key: str, data: dict):
    _cache[key] = (time.monotonic(), data)


# ── 抓取 ──

async def _fetch_json(url: str, referer: str | None = None) -> dict:
    """抓取 JSON/JSONP 接口，剥掉外层包装后解析为 dict。"""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    text = resp.text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"响应不是 JSON: {text[:100]!r}")
    return json.loads(text[start:end + 1])


# ── 时间工具 ──

def _bj_to_naive_utc(time_str: str, fmt: str) -> datetime | None:
    """北京时间字符串 → naive UTC datetime。"""
    try:
        return datetime.strptime(time_str, fmt) - BEIJING_OFFSET
    except (ValueError, TypeError):
        return None


def _iso(dt: datetime | None) -> str:
    """naive UTC datetime → ISO 字符串（带 Z，前端可直接 new Date 解析为 UTC）。"""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def _iso_to_dt(s: str) -> datetime | None:
    """ISO 字符串（带 Z）→ naive UTC datetime（存档入库用）。"""
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


# ── 台风解析 ──

def _parse_typhoon_list(raw: dict) -> list[dict]:
    """list_default 的 typhoonList: [id, 英文名, 中文名, 编号, 编号2, 编号3, 描述, 状态]。"""
    out = []
    for item in raw.get("typhoonList", []):
        out.append({
            "id": str(item[0]),
            "name_en": item[1] or "nameless",
            "name": item[2] or "热带低压",
            "status": item[7] or "stop",
        })
    return out


def _parse_radii(radii: list) -> tuple[float | None, float | None]:
    """风圈半径 [["30KTS", NE, SE, SW, NW, pointId], ...] → (7级均值, 10级均值)，单位 km。"""
    r7 = r10 = None
    for r in radii or []:
        quads = [float(x) for x in r[1:5] if isinstance(x, (int, float)) and x > 0]
        if not quads:
            continue
        avg = sum(quads) / len(quads)
        if r[0] == "30KTS":
            r7 = avg
        elif r[0] == "50KTS":
            r10 = avg
    return r7, r10


def _parse_typhoon_view(raw: dict) -> dict:
    """view_{id} 的 typhoon 字段: [id, 英文名, 中文名, ..., 状态, [轨迹点], [关联]]。

    轨迹点: [点ID, 时间, epochMs, 强度, lng, lat, 气压, 风速, 移向, 移速, 风圈[], 预报{}, null]
    预报:   {"BABJ": [[提前小时, 发布时间, lng, lat, 气压, 风速, 机构, 强度], ...]}
            有效时间 = 发布时间 + 提前小时；只取最后实况点携带的最新一报，避免历史各报重叠
    """
    t = raw["typhoon"]
    header = {
        "id": str(t[0]),
        "name_en": t[1] or "nameless",
        "name": t[2] or "热带低压",
        "status": t[7] or "stop",
    }
    observed = []
    for p in t[8] or []:
        obs_time = _bj_to_naive_utc(str(p[1]), "%Y%m%d%H%M")
        r7, r10 = _parse_radii(p[10])
        observed.append({
            "lat": float(p[5]), "lng": float(p[4]),
            "pressure": p[6] if isinstance(p[6], (int, float)) else None,
            "wind_speed": p[7] if isinstance(p[7], (int, float)) else None,
            "level": str(p[3]), "level_label": LEVEL_LABELS.get(str(p[3]), str(p[3])),
            "move_dir": p[8] or "", "move_speed": p[9] if isinstance(p[9], (int, float)) else None,
            "radius7": r7, "radius10": r10,
            "obs_time": _iso(obs_time), "is_forecast": False,
        })
    # 预报：只取最后实况点携带的最新一报
    forecast = []
    if t[8]:
        for agency_points in (t[8][-1][11] or {}).values():
            for f in agency_points:
                base = _bj_to_naive_utc(str(f[1]), "%Y%m%d%H%M")
                lead = f[0] if isinstance(f[0], (int, float)) else None
                valid = base + timedelta(hours=lead) if (base and lead is not None) else None
                forecast.append({
                    "lat": float(f[3]), "lng": float(f[2]),
                    "pressure": f[4] if isinstance(f[4], (int, float)) else None,
                    "wind_speed": f[5] if isinstance(f[5], (int, float)) else None,
                    "level": str(f[7]), "level_label": LEVEL_LABELS.get(str(f[7]), str(f[7])),
                    "obs_time": _iso(valid), "is_forecast": True,
                })
    # 统一按时间排序（ISO 字符串可直接字典序比较），丢弃时间解析失败的点
    track = sorted(
        (x for x in observed + forecast if x["obs_time"]),
        key=lambda x: x["obs_time"],
    )
    current = observed[-1] if observed else None
    # 最后实况点可能无风圈数据（台风减弱时），向前回退找最近一次
    if current and current["radius7"] is None and current["radius10"] is None:
        for prev in reversed(observed[:-1]):
            if prev["radius7"] is not None or prev["radius10"] is not None:
                current = {**current, "radius7": prev["radius7"], "radius10": prev["radius10"]}
                break
    return {
        **header,
        "current": current,
        "track": track,
        "degraded": False,
    }


# ── 预警解析 ──

_WARNING_TITLE_RE = re.compile(r"^(?P<by>.+?)发布(?P<rest>.+?)(?P<level>蓝色|黄色|橙色|红色)预警")


def _parse_warnings(raw: dict) -> list[dict]:
    """grepalarm_cn.php 的 alarminfo: {count, data: [[地区, url, lng, lat, alertid, alertid2, 标题], ...]}。"""
    out = []
    for item in raw.get("data", []) or []:
        title = item[6] or ""
        m = _WARNING_TITLE_RE.match(title)
        if not m:
            continue
        issued_at = _bj_to_naive_utc(str(item[4]).rsplit("_", 1)[-1], "%Y%m%d%H%M%S")
        try:
            lat, lng = float(item[3]), float(item[2])
        except (ValueError, TypeError):
            lat = lng = None
        out.append({
            "id": str(item[4]),
            "type": m.group("rest").rstrip("气象").rstrip("信号") or m.group("rest"),
            "level": m.group("level"),
            "level_code": WARNING_LEVEL_CODES.get(m.group("level"), ""),
            "title": title,
            "region": item[0] or "",
            "lat": lat, "lng": lng,
            "issued_by": m.group("by"),
            "issued_at": _iso(issued_at),
        })
    return out


# ── 存档 ──

async def _upsert_track_points(typhoon_id: str, name: str, points: list[dict]):
    """轨迹点 upsert 到 typhoon_tracks（唯一约束 typhoon_id + obs_time + is_forecast）。"""
    async with async_session() as session:
        for p in points:
            obs_time = _iso_to_dt(p.get("obs_time") or "")
            if obs_time is None:
                continue
            values = dict(
                typhoon_id=typhoon_id, name=name,
                obs_time=obs_time, lat=p["lat"], lng=p["lng"],
                pressure=p.get("pressure"), wind_speed=p.get("wind_speed"),
                level=p.get("level"), is_forecast=bool(p.get("is_forecast")),
                radius7=p.get("radius7"), radius10=p.get("radius10"),
            )
            stmt = sqlite_insert(TyphoonTrack).values(**values).on_conflict_do_update(
                index_elements=["typhoon_id", "obs_time", "is_forecast"],
                set_={k: v for k, v in values.items() if k != "typhoon_id"},
            )
            await session.execute(stmt)
        await session.commit()


async def _archived_from_db(exclude_ids: set[str]) -> list[dict]:
    """存档台风列表（按最后实况点倒序）。"""
    async with async_session() as session:
        rows = (
            await session.execute(
                select(
                    TyphoonTrack.typhoon_id,
                    func.max(TyphoonTrack.name),
                    func.min(TyphoonTrack.obs_time),
                    func.max(TyphoonTrack.obs_time),
                    func.count(),
                )
                .where(TyphoonTrack.is_forecast.is_(False))
                .group_by(TyphoonTrack.typhoon_id)
                .order_by(func.max(TyphoonTrack.obs_time).desc())
            )
        ).all()
    out = []
    for tid, name, started, ended, count in rows:
        if tid in exclude_ids:
            continue
        out.append({
            "id": tid, "name": name or "", "name_en": "",
            "status": "stop", "track_points": count,
            "started_at": _iso(started), "ended_at": _iso(ended),
        })
    return out


# ── 台风影响城市 ──

AFFECTED_WINDOW_HOURS = 48       # 只看当前实况点 + 48h 内预报点
AFFECTED_RADIUS_FALLBACK_KM = 300.0


def _compute_affected_cities(detail: dict) -> list[dict]:
    """台风影响城市：实况点 + 48h 预报点，城市与任一轨迹点距离 ≤ 7 级风圈半径（缺数据 300km）。"""
    from services.geo import GEO_CITY_MAP, haversine_km

    track = detail.get("track") or []
    if not track:
        return []
    observed = [p for p in track if not p.get("is_forecast")]
    latest_obs = observed[-1] if observed else track[-1]
    cutoff_dt = _iso_to_dt(latest_obs.get("obs_time") or "")
    if cutoff_dt is None:
        return []
    cutoff_dt += timedelta(hours=AFFECTED_WINDOW_HOURS)
    window_points = [
        p for p in track
        if p.get("obs_time") and (_iso_to_dt(p["obs_time"]) or datetime.min) <= cutoff_dt
    ]
    radius = float((detail.get("current") or {}).get("radius7") or AFFECTED_RADIUS_FALLBACK_KM)
    affected = []
    for name, (lat, lng, _en) in GEO_CITY_MAP.items():
        best_dist, best_time = None, None
        for p in window_points:
            d = haversine_km(lat, lng, p["lat"], p["lng"])
            if best_dist is None or d < best_dist:
                best_dist, best_time = d, p["obs_time"]
        if best_dist is not None and best_dist <= radius:
            affected.append({
                "name": name, "lat": lat, "lng": lng,
                "est_time": best_time, "distance": round(best_dist),
            })
    affected.sort(key=lambda c: c["distance"])
    return affected


# ── 对外接口 ──

async def get_typhoons() -> dict:
    """活跃台风（NMC 列表）+ 存档台风（本地库）列表。"""
    key = "typhoon_list"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache_get(key)
        if cached:
            return cached
        result = {"active": [], "archived": [], "degraded": False}
        try:
            raw = await _fetch_json(TYPHOON_LIST_URL)
            parsed = _parse_typhoon_list(raw)
            result["active"] = [t for t in parsed if t["status"] == "start"]
        except Exception as e:
            logger.warning(f"获取台风列表失败: {e}")
            # 保留上次快照
            prev = _cache.get(key)
            if prev:
                return {**prev[1], "degraded": True}
            result["degraded"] = True
        # 存档列表来自本地库，不受 NMC 故障影响
        try:
            active_ids = {t["id"] for t in result["active"]}
            result["archived"] = await _archived_from_db(active_ids)
        except Exception as e:
            logger.warning(f"读取台风存档失败: {e}")
        _cache_set(key, result)
        return result


async def get_typhoon_detail(typhoon_id: str) -> dict:
    """单台风轨迹 + 风圈详情（NMC 优先，失败时回退本地存档）。"""
    key = f"typhoon_view:{typhoon_id}"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache_get(key)
        if cached:
            return cached
        try:
            raw = await _fetch_json(TYPHOON_VIEW_URL.format(id=typhoon_id))
            detail = _parse_typhoon_view(raw)
            detail["affected_cities"] = _compute_affected_cities(detail)
            # 顺带存档（实况 + 预报点）
            try:
                await _upsert_track_points(typhoon_id, detail["name"], detail["track"])
            except Exception as e:
                logger.warning(f"台风轨迹存档失败: {e}")
            _cache_set(key, detail)
            return detail
        except Exception as e:
            logger.warning(f"获取台风 {typhoon_id} 轨迹失败: {e}")
            prev = _cache.get(key)
            if prev:
                return {**prev[1], "degraded": True}
            return await _detail_from_db(typhoon_id)


async def _detail_from_db(typhoon_id: str) -> dict:
    """NMC 不可用时从本地存档构造详情（仅实况点，无预报/风圈）。"""
    async with async_session() as session:
        rows = (
            await session.execute(
                select(TyphoonTrack).where(TyphoonTrack.typhoon_id == typhoon_id)
                .order_by(TyphoonTrack.obs_time.asc())
            )
        ).scalars().all()
    if not rows:
        return {"id": typhoon_id, "name": "", "name_en": "", "current": None, "track": [], "degraded": True}
    track = [{
        "lat": r.lat, "lng": r.lng, "pressure": r.pressure, "wind_speed": r.wind_speed,
        "level": r.level or "", "level_label": LEVEL_LABELS.get(r.level or "", r.level or ""),
        "radius7": r.radius7, "radius10": r.radius10,
        "obs_time": _iso(r.obs_time), "is_forecast": bool(r.is_forecast),
    } for r in rows]
    observed = [t for t in track if not t["is_forecast"]]
    detail = {
        "id": typhoon_id, "name": rows[0].name or "", "name_en": "",
        "current": observed[-1] if observed else None,
        "track": track, "degraded": False,
    }
    detail["affected_cities"] = _compute_affected_cities(detail)
    return detail


async def get_warnings() -> dict:
    """当前生效极端天气预警列表（含经纬度，前端直接打点）。"""
    key = "warnings"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache_get(key)
        if cached:
            return cached
        try:
            raw = await _fetch_json(WARNINGS_URL, referer="http://www.weather.com.cn/")
            parsed = _parse_warnings(raw)
            parsed.sort(key=lambda w: w["issued_at"], reverse=True)
            result = {"warnings": parsed[:MAX_WARNINGS], "total": len(parsed), "degraded": False}
        except Exception as e:
            logger.warning(f"获取预警失败: {e}")
            prev = _cache.get(key)
            if prev:
                return {**prev[1], "degraded": True}
            result = {"warnings": [], "total": 0, "degraded": True}
        _cache_set(key, result)
        return result
