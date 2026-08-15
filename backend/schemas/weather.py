from pydantic import BaseModel


class TyphoonSummary(BaseModel):
    """台风摘要（活跃/存档列表项）。"""
    id: str
    name: str
    name_en: str
    status: str                      # start / stop
    track_points: int = 0            # 已存档轨迹点数
    started_at: str | None = None    # 首个实况点时间 (ISO, UTC)
    ended_at: str | None = None      # 最后实况点时间 (ISO, UTC)


class TyphoonCurrent(BaseModel):
    """台风当前实况。"""
    lat: float
    lng: float
    pressure: float | None = None
    wind_speed: float | None = None
    level: str = ""
    level_label: str = ""
    move_dir: str = ""
    move_speed: float | None = None
    radius7: float | None = None
    radius10: float | None = None
    obs_time: str = ""               # ISO (UTC)


class TyphoonTrackPoint(BaseModel):
    """轨迹点（实况或预报）。"""
    lat: float
    lng: float
    pressure: float | None = None
    wind_speed: float | None = None
    level: str = ""
    obs_time: str = ""               # ISO (UTC)
    is_forecast: bool = False


class TyphoonAffectedCity(BaseModel):
    """台风影响城市（48h 窗口内与轨迹点距离 ≤ 7 级风圈半径）。"""
    name: str
    lat: float
    lng: float
    est_time: str = ""               # 最近轨迹点时间 (ISO, UTC)
    distance: int = 0                # 与轨迹点最近距离 km


class TyphoonDetail(BaseModel):
    """单台风轨迹 + 风圈详情。"""
    id: str
    name: str
    name_en: str
    current: TyphoonCurrent | None = None
    track: list[TyphoonTrackPoint] = []
    affected_cities: list[TyphoonAffectedCity] = []
    degraded: bool = False


class TyphoonListResponse(BaseModel):
    active: list[TyphoonSummary] = []
    archived: list[TyphoonSummary] = []
    degraded: bool = False


class WeatherWarning(BaseModel):
    """极端天气预警。"""
    id: str
    type: str                        # 台风/暴雨/高温/雷电/寒潮...
    level: str                       # 蓝色/黄色/橙色/红色
    level_code: str                  # blue/yellow/orange/red
    title: str
    region: str                      # 地区名（如"山东省济宁市鱼台县"）
    lat: float | None = None
    lng: float | None = None
    issued_by: str = ""              # 发布单位
    issued_at: str = ""              # 发布时间


class WarningsResponse(BaseModel):
    warnings: list[WeatherWarning] = []
    total: int = 0
    degraded: bool = False
