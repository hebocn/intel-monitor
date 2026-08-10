# 首页驾驶舱完整改造方案

> 创建时间: 2026-08-07
> 状态: 已完成实施

---

## 目标

将当前首页（`CockpitPage.tsx`）从仅展示 2 个 API 数据的稀疏布局，改造为充分利用项目中 12 个 API 模块的全景驾驶舱。

---

## 当前状态分析

### 已展示的数据（仅 2 个 API）
- `dashboardAPI.get()` → 6 个 KPI 卡片 + 最近 20 条监测结果
- `scheduleAPI.status()` → 活跃任务队列

### 已存在但未展示的数据（10 个 API 模块未被使用）
- `targetsAPI` / `websitesAPI` — 监测目标详情
- `resultsAPI` — 监测结果查询、评论数据
- `hotTopicsAPI` — 16 个平台的热门话题
- `sentimentAPI` — 舆情搜索任务、影响力评分
- `intelligenceAPI` — 情报报告生成进度
- `accountMatchAPI` — 跨平台账号匹配
- `settingsAPI` — AI 引擎配置、系统状态
- 系统工具端点 — OpenCLI 状态、Chrome CDP 状态

### 当前问题
1. 24H 趋势图使用 `Math.sin()` + `Math.random()` 伪造数据
2. 平台延迟值硬编码（`<200ms` / `1.2s` / `--`）
3. 状态栏 AI ENGINE 字段硬编码 `--`
4. 右侧面板内容稀疏（IDLE 状态下几乎为空）

---

## 新首页布局

```
┌─────────────────────────────────────────────────────────────┐
│  TOP BAR: ◆ INTEL COCKPIT    SYSTEM OPERATIONAL    14:32:05 │
├─────────────────────────────────────────────────────────────┤
│  KPI ROW — 6 cards (保持不变)                                │
│  [监测目标] [活跃目标] [网站监测] [今日监测] [成功] [失败]      │
├────────────────────────────┬────────────────────────────────┤
│  平台监测状态                │  实时热点 TOP5  ← 新增           │
│  · 摘要行 (Platforms/Events │  · 各平台最热话题                │
│    /Success%)              │  · hot_value + 排名             │
│  · 平台网格 (6 items)       │  · 点击跳转原文                  │
│  · 24H 趋势图 (真实数据) ←改│                                │
├────────────────────────────┼────────────────────────────────┤
│  活跃任务队列                │  系统健康 & 舆情概况  ← 新增     │
│  · 调度任务列表              │  · OpenCLI Daemon ●/○          │
│  · 平台分布环形图 (已有)     │  · Chrome CDP ●/○              │
│                             │  · AI Engine: DeepSeek/MiniMax │
│                             │  · 爬取方法分布 (opencli/cdp/  │
│                             │    playwright 占比)             │
│                             │  · 本周舆情搜索数               │
│                             │  · 情报报告生成中               │
├────────────────────────────┴────────────────────────────────┤
│  最近监测结果 · SIGNAL FEED (保持不变)                        │
├─────────────────────────────────────────────────────────────┤
│  STATUS BAR: SYS.ID │ UPTIME │ AI ENGINE │ TARGETS │        │
│              TODAY RESULTS │ SUCCESS RATE                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 后端改造

### 1. 扩展 `GET /api/dashboard` 响应
在 `backend/routers/dashboard.py` 中新增字段：

```python
# 新增字段
- trend_data: List[{date, total, success, failed}]  # 最近 7 天每日统计
- crawl_method_stats: {opencli, cdp, playwright, scrapling}  # 爬取方法分布
- platform_stats: [{platform, count, success_rate}]  # 各平台统计
```

### 2. 新增 `GET /api/dashboard/overview`
聚合端点，一次返回首页需要的所有跨模块摘要：

```python
- hot_topics_preview: [{title, platform, hot_value, rank, url}]  # 各平台 TOP1
- sentiment_summary: {total_tasks, total_posts, this_week_tasks}
- intelligence_summary: {total_reports, in_progress, completed}
- system_health: {opencli_running, cdp_connected, ai_provider, ai_model}
- account_match_summary: {total_tasks, recent_matches}
```

### 3. 文件变更清单
| 文件 | 操作 |
|------|------|
| `backend/routers/dashboard.py` | 扩展 + 新增 endpoint |
| `backend/schemas/dashboard.py` | 新增 response models |
| `backend/services/` | 如需要，抽取聚合逻辑 |

---

## 前端改造

### 新增面板

| 面板 | 位置 | 数据来源 | 组件 |
|------|------|----------|------|
| 实时热点 TOP5 | 右上（原"活跃任务"位置） | `hotTopicsAPI.listTopics()` | `HotTopicsPanel` |
| 系统健康 & 舆情概况 | 右下（新占位） | `/api/dashboard/overview` | `SystemHealthPanel` |

### 修改面板

| 面板 | 改动 |
|------|------|
| 平台监测状态 | 24H 趋势替换为真实数据；延迟值改为真实爬取耗时 |
| 状态栏 | AI ENGINE 字段接入 `/api/settings/active` |

### 布局调整

当前为 2 列 grid（`grid-template-columns: 1fr 1fr`），保持不变。左侧面板和右侧面板重新配对：

- **左上**: 平台监测状态（增强）
- **右上**: 实时热点 TOP5（替换原"活跃任务"）
- **左下**: 活跃任务队列（保留，移到左下）
- **右下**: 系统健康 & 舆情概况（替换原"平台分布"，环形图移入平台监测面板）

### 文件变更清单
| 文件 | 操作 |
|------|------|
| `frontend/src/pages/CockpitPage.tsx` | 新增面板组件、替换假数据、布局重组 |
| `frontend/src/pages/CockpitPage.css` | 新增面板样式 |
| `frontend/src/services/api.ts` | 如需要，补充 API 调用 |

---

## 实施顺序

1. **后端** — 扩展 `/api/dashboard` + 新增 `/api/dashboard/overview`
2. **前端 API** — 补充 `api.ts` 中的调用函数
3. **前端面板** — 逐个新建面板组件
4. **前端集成** — 替换假数据、重组布局
5. **调试** — TypeScript 检查、视觉微调、响应式

---

## 预估工时

| 阶段 | 内容 | 时间 |
|------|------|------|
| 后端 | 扩展 dashboard API + 新增 overview 端点 | 1-1.5h |
| 前端面板 | 4 个新/改面板组件 | 2-3h |
| 前端集成 | 数据接入、布局重组、状态栏修复 | 1h |
| 调试打磨 | TS 检查、视觉微调、响应式 | 0.5h |
| **合计** | | **4.5-6h** |

---

## 依赖与风险

- 无外部依赖，纯项目内改造
- 所有新增数据均来自已有数据表和 API
- 不修改数据库 schema
- 不影响现有监测、爬虫、调度功能
- 前端仅新增 CSS 类，不引入第三方图表库
