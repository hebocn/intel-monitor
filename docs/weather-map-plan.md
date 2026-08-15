# Leaflet 地图台风/极端天气可视化方案

> 创建时间: 2026-08-14
> 状态: 已实施（2026-08-14 完成 Phase 1-4 并端到端验证）
> 落地位置: `intel-map`（`/neo/`，端口 3001）— 主前端 CockpitPage 不动

---

## 目标

在 intel-map 的 Leaflet 地图上新增**台风/极端天气专项可视化**：
台风路径（实况 + 预报 + 风圈）+ 中央气象台全部极端天气预警（台风/暴雨/高温/寒潮等），
与现有情报信号联动（风圈内信号高亮 + 计数）。

---

## 设计决策（经需求访谈确认）

| 决策点 | 结论 |
|--------|------|
| 定位 | 台风/极端天气专项，非泛气象图层 |
| 数据源 | 中央气象台 NMC（免费、无 Key、未文档化接口，Phase 1 先探测验证） |
| 覆盖范围 | 台风路径（实况+预报+风圈）+ 全部预警，分阶段落地 |
| 台风渲染 | 实况实线 + 预报虚线 + 7/10 级风圈（`L.circle`）+ 按强度着色标记 + popup 详情 |
| 预警渲染 | 地图内右侧浮层列表 + 城市标记（蓝/黄/橙/红分级） |
| 刷新机制 | 后端内存 TTL 缓存 10 分钟 + 前端 10 分钟轮询 + 手动刷新 |
| 历史存档 | 每次抓取 upsert 进新表 `typhoon_tracks`（新建表，create_all 自动建）；预警不存档 |
| UI 入口 | 地图页头「台风」「预警」开关 + 历史台风下拉；预警浮层复用 Hot Cities 浮层样式 |
| 信号联动 | 风圈内信号点高亮 + 页头「受影响信号 N 个」计数（纯前端 haversine） |
| 失败兜底 | 优雅降级：返回 `degraded: true` + 保留上次成功快照，不引入第二数据源 |

---

## 后端改造

### 1. 数据模型 — `backend/models/typhoon.py`（新建）

```python
class TyphoonTrack(Base):
    __tablename__ = "typhoon_tracks"

    id = Column(Integer, primary_key=True)
    typhoon_id = Column(String(16), index=True)     # NMC 台风编号
    name = Column(String(64))                        # 中文名（如"悟空"）
    obs_time = Column(DateTime)                      # naive UTC（项目红线）
    lat = Column(Float)
    lng = Column(Float)
    pressure = Column(Float, nullable=True)          # 中心气压 hPa
    wind_speed = Column(Float, nullable=True)        # 最大风速 m/s
    level = Column(String(16))                       # TD/TS/STS/TY/STY/SuperTY
    is_forecast = Column(Boolean, default=False)     # 预报点 or 实况点
    radius7 = Column(Float, nullable=True)           # 7 级风圈半径 km
    radius10 = Column(Float, nullable=True)          # 10 级风圈半径 km
    created_at = Column(DateTime, default=...)

    __table_args__ = (UniqueConstraint("typhoon_id", "obs_time", "is_forecast"),)
```

- 新表由 `database.py:22` 的 `Base.metadata.create_all` 启动时自动创建，**不涉及现有表 ALTER**
- upsert 用唯一约束 `(typhoon_id, obs_time, is_forecast)` 做冲突更新，避免重复抓取时产生重复点

### 2. 服务层 — `backend/services/weather.py`（新建）

职责：抓取 + 解析 + TTL 缓存 + 存档。业务逻辑全部在此（遵守"不在 routers/ 写业务逻辑"红线）。

```python
async def get_typhoons() -> dict      # 活跃台风列表 + 存档列表 + degraded 标记
async def get_typhoon_detail(typhoon_id: str) -> dict  # 单台风轨迹 + 风圈详情
async def get_warnings() -> dict      # 当前生效预警列表 + degraded 标记
```

- **缓存**: 模块级 `{key: (timestamp, data)}` 内存缓存，TTL 10 分钟，过期惰性重抓
- **存档**: 每次抓取活跃台风时 upsert 轨迹点到 `typhoon_tracks`
- **抓取**: `httpx.AsyncClient`，设置浏览器 UA（NMC 可能校验 Referer/UA）
- **时区**: NMC 时间为北京时间，统一转 naive UTC 存储（遵守爬虫 `published_at` 同类红线）
- **降级**: 抓取/解析异常时返回 `{"degraded": True, ...}` + 上次成功快照，记录 `error_log` 日志

### 3. NMC 数据接口（Phase 1 实测探测验证）

候选端点（未文档化，实现时先探测确认可用性与字段结构）：

| 用途 | 候选接口 |
|------|----------|
| 活跃台风列表 | `https://typhoon.nmc.cn/weatherservice/typhoon/jsons/list_default` |
| 单台风轨迹+预报+风圈 | `https://typhoon.nmc.cn/weatherservice/typhoon/jsons/view_{id}` |
| 全部预警 | `http://www.nmc.cn/rest/findAlarm` |

- 若候选端点失效，用浏览器实际访问 `nmc.cn`/`typhoon.nmc.cn` 抓真实请求路径（可用项目 web-access skill 的 CDP 能力）
- 风圈半径字段可能按 NE/SE/SW/NW 四象限给出，v1 取平均值画圆即可（象限风圈留作后续增强）

### 4. 路由 — `backend/routers/weather.py`（新建）

薄路由，只做参数校验 + 调 service（**免认证**，与 `/api/dashboard/geo-signals` 一致）：

```python
router = APIRouter(prefix="/api/weather", tags=["weather"])

@router.get("/typhoons")              # 活跃 + 存档台风列表
@router.get("/typhoons/{typhoon_id}") # 单台风轨迹 + 风圈详情
@router.get("/warnings")              # 当前生效预警
```

响应统一带 `degraded: bool` 字段；`main.py` 挂载路由。

### 5. API 响应形状

`GET /api/weather/typhoons`:
```json
{
  "active": [{"id": "2425", "name": "悟空", "name_en": "WUKONG", "updated_at": "2026-08-14T12:00:00Z"}],
  "archived": [{"id": "2418", "name": "海棠", "track_points": 42, "started_at": "...", "ended_at": "..."}],
  "degraded": false
}
```

`GET /api/weather/typhoons/{id}`:
```json
{
  "id": "2425", "name": "悟空", "name_en": "WUKONG",
  "current": {"lat": 21.5, "lng": 125.3, "pressure": 965, "wind_speed": 38,
              "level": "TY", "level_label": "台风级", "move_dir": "西北",
              "move_speed": 15, "radius7": 280, "radius10": 100,
              "obs_time": "2026-08-14T12:00:00Z"},
  "track": [{"lat": 21.5, "lng": 125.3, "pressure": 965, "wind_speed": 38,
             "level": "TY", "obs_time": "...", "is_forecast": false}],
  "degraded": false
}
```

`GET /api/weather/warnings`:
```json
{
  "warnings": [{"id": "...", "type": "台风", "level": "蓝色", "level_code": "blue",
                "title": "...", "region": "福建省", "city": "福州",
                "lat": 26.1, "lng": 119.3, "issued_by": "福建省气象台",
                "issued_at": "...", "content": "..."}],
  "degraded": false
}
```

- `city/lat/lng`: 用 `backend/routers/dashboard.py:410` 的 `GEO_CITY_MAP` 从预警地区文本解析（从 routers 导入或提取到共享模块）
- 解析不到城市的预警**只进列表、不打点**（降级逻辑）

---

## 前端改造（intel-map `src/App.tsx`）

### 地图页头新增控件

```
┌─────────────────────────────────────────────────────────────┐
│ Global Intelligence Map                    [台风][预警][历史▾] │
│ [WB][X][XHS][DY][YT][WEB] | [政治][经济]... | [刷新] 128 signals │
└─────────────────────────────────────────────────────────────┘
```

- **「台风」开关**: 控制台风图层显隐（默认关）
- **「预警」开关**: 控制预警浮层 + 城市标记显隐（默认关）
- **「历史」下拉**: 默认"当前活跃台风"，可选存档台风查看其轨迹
- 开关打开且数据 degraded 时显示「气象数据不可用」小字提示

### 台风图层（开关打开时渲染）

- **路径**: `L.polyline` 实况段实线、预报段虚线（`dashArray: '6 6'`）
- **风圈**: 当前实况点 `L.circle` 半透明双层（radius7 外圈、radius10 内圈），带脉冲样式
- **强度标记**: 历史点 `L.circleMarker`，按强度分级着色：

| 级别 | TD 热带低压 | TS 热带风暴 | STS 强热带风暴 | TY 台风 | STY 强台风 | SuperTY 超强台风 |
|------|-------------|-------------|----------------|---------|------------|------------------|
| 颜色 | `#9CA3AF` | `#4ADE80` | `#FACC15` | `#FB923C` | `#F87171` | `#C084FC` |

- **popup**: 名称/编号、气压、最大风速、移向移速、7/10 级风圈半径、观测时间（北京时间展示）
- 图层组用 `L.layerGroup` 管理，切换开关/历史台风时统一清空重建

### 预警浮层（开关打开时渲染）

- 地图内右侧浮层（复用现有 `.map-hot-city` 浮层样式），列出当前生效预警：
  类型徽章 + 级别色条 + 地区 + 发布单位 + 时间，按级别排序（红>橙>黄>蓝）
- 城市标记: 解析出坐标的预警在地图上打点，颜色按级别：

| 级别 | 蓝色 | 黄色 | 橙色 | 红色 |
|------|------|------|------|------|
| 颜色 | `#4FC3F7` | `#FFD54F` | `#FF9800` | `#F44336` |

- 点击浮层条目 → 地图 pan 到对应城市标记并弹详情

### 信号联动（台风开关打开时生效）

- 对每个信号点做 haversine 距离计算：`dist(signal, 台风当前中心) <= max(radius7, radius10)` → 信号点高亮（放大 + 描边）
- 页头信号计数器旁显示「受影响信号 N 个」
- 纯前端计算，后端零改动；每次台风数据更新或信号过滤变化时重算

### 数据获取

- `fetchAll()` 中并行拉取 `/api/weather/typhoons` + `/api/weather/warnings`
- 选中台风时按需拉 `/api/weather/typhoons/{id}`
- 新增 10 分钟 `setInterval` 轮询气象数据；现有页头「刷新」按钮同时刷新气象
- degraded 时保留上次成功数据快照，仅提示不可用

---

## 分阶段实施

| 阶段 | 内容 | 完成标志 |
|------|------|----------|
| **Phase 1** 后端 | 探测验证 NMC 接口 → models + schemas + `services/weather.py` + `routers/weather.py` + main.py 挂载 | `/api/weather/*` 三端点返回真实数据，`typhoon_tracks` 表开始积累 |
| **Phase 2** 台风图层 | 页头「台风」开关 + 路径线/风圈/强度标记/popup + 历史下拉 | 地图上可查看当前台风轨迹与风圈 |
| **Phase 3** 预警 | 「预警」开关 + 浮层列表 + 城市标记 + GEO_CITY_MAP 解析 | 预警按级别着色显示在地图和浮层 |
| **Phase 4** 联动 | 风圈内信号高亮 + 「受影响信号」计数 + degraded 状态 UI | 台风接近时信号点高亮、计数实时更新 |

---

## 风险与已知限制

1. **NMC 接口未文档化** — Phase 1 首要任务是用真实请求探测端点与字段结构；接口变动会导致数据抓取失败（此时走 degraded 降级，不崩溃）
2. **预警地区文本解析** — `GEO_CITY_MAP` 约 60+ 主要城市，县/区级预警匹配不上 → 只进列表不打点；后续可按需扩充地图词表
3. **历史存档空洞** — 台风消亡后 NMC 不再提供更新，已存档轨迹的尾部会有数据空洞（已接受的代价）；预警不做存档
4. **风圈四象限** — NMC 风圈半径若按 NE/SE/SW/NW 给出，v1 取平均值画圆，精度略降
5. **后端重启需全杀 Python** — 新增路由后按项目红线执行 `taskkill /F /IM python.exe` 再重启，避免 reload 模式旧 worker 残留
