# Intel Monitor — 项目约定

> 社交媒体情报监控平台：FastAPI 后端 + React/Ant Design 前端
>
> **详细开发手册：** [`docs/development-guide.md`](docs/development-guide.md) — 启动方式、配置、架构、功能实现、数据库模式、已知问题

## 平台与环境

本项目运行在 **Windows** 上。
- 始终使用 PowerShell 命令而非 bash
- 不使用 Unix 专用语法（`export`、`source`、`~/.bashrc`）
- 环境变量用 `$env:VAR`，链式命令用 `;` 或换行，路径用 Windows 格式

## 架构提案要求

提出架构变更时，不要给浅层第一方案。必须做到：
- 列出 2-3 种可选模式，每种给出具体优缺点（代码层面，不是泛泛而谈）
- 结合当前代码库的具体情况论证选择
- 说明迁移成本和对现有功能的影响
- 不确定就问，不要默默选一个

## 插件/技能管理

检查或修改 Claude Code 设置时，始终**同时检查** `~/.claude/settings.json` 和 `~/.claude/settings.local.json`。设置可能分散在两个文件中。修复插件问题时，统一合并到 `settings.local.json` 以避免升级时丢失。

## 快速启动

```bash
cd intel-monitor && start.bat          # 启动后端 (localhost:8000) + 前端 (localhost:3000)
# 或手动：
cd backend && python main.py           # 后端
cd frontend && npm run dev             # 前端 (Vite dev server, 热更新)
```

**注意：** 生产模式下 (`start.bat`), 修改前端源码后需 `cd frontend && npm run build` 重建 dist。

## 技术栈

- **后端:** Python 3.14, FastAPI, SQLAlchemy async (aiosqlite), APScheduler
- **前端:** React 18, Ant Design 5, Vite, Axios
- **数据库:** SQLite (`backend/data/intel_monitor.db`)
- **爬虫:** OpenCLI → CDP → Scrapling → Playwright (降级链)。Scrapling 提供 stealth browser 免 CDP 登录，仅用于今日头条（2026-06-20 集成）
- **热门话题:** AutoCLI (Chrome CDP 复用登录态，支持 16 个平台)。微博热搜在 AutoCLI 不可用时自动降级到 Playwright headless 模式
- **AI 摘要:** MiniMax / DeepSeek / MiMo (OpenAI 兼容格式，支持多模态图片分析，通过 `AI_PROVIDER` 切换，模型名和 system prompt 可在系统设置中自定义)
- **UI 主题:** 森林绿 (`#2d6a4f`) 为主，热门话题页独立浅色毛玻璃主题 + 平台专属配色

## 目录结构

```
backend/
  main.py           # FastAPI 入口 + 路由挂载
  config.py         # 环境变量 (DATABASE_URL, HOST, PORT, SECRET_KEY, AI_PROVIDER)
  database.py       # SQLAlchemy async engine + session
  auth.py           # JWT 认证 (bcrypt + JWT)
  models/           # ORM 模型 (Target, WebsiteTarget, MonitorResult, HotComment, HotTopic, HotTopicSource, User, SentimentTask, SentimentPost, PlatformStats)
  schemas/          # Pydantic 请求/响应模型
  routers/          # API 路由 (auth, targets, websites, results, dashboard, schedule, settings, tools, hot_topics, sentiment)
  services/         # 业务逻辑 (monitor, scheduler, summarizer, autocli_service, sentiment, scoring)
  crawlers/         # 爬虫实现 (router, opencli, cdp, claude, scrapling base, x, youtube, xiaohongshu, douyin, weibo, toutiao, tiantai108)
  data/             # SQLite 数据库文件
frontend/
  src/pages/        # 页面组件 (Dashboard, SocialAccounts, Websites, Settings, Login, MonitorDetail, HotTopicsPage, SentimentPage)
  src/components/   # 共享组件 (AppLayout, ProtectedRoute)
  src/services/     # API 客户端
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/intel_monitor.db` | 数据库连接 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8000` | 监听端口 |
| `AI_PROVIDER` | `minimax` | 默认 AI 提供商 (minimax/deepseek/mimo) |
| `MINIMAX_API_KEY` | (无) | MiniMax API Key |
| `MINIMAX_BASE_URL` | `https://api.minimaxi.com/v1/chat/completions` | MiniMax API 端点 |
| `MINIMAX_MODEL` | `MiniMax-M2.7` | MiniMax 模型 |
| `DEEPSEEK_API_KEY` | (无) | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型 |
| `MIMO_API_KEY` | (无) | MiMo API Key |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | MiMo API 端点 |
| `MIMO_MODEL` | `mimo-v2.5-pro` | MiMo 模型 |
| `SUMMARIZE_POSTS_PROMPT` | (见代码默认值) | 贴文分析 system prompt |
| `SUMMARIZE_WEBSITE_PROMPT` | (见代码默认值) | 网站分析 system prompt |

## API 路由清单

| 前缀 | 文件 | 说明 |
|------|------|------|
| `/api/auth` | `routers/auth.py` | 认证 (setup, login, register, reset-password) |
| `/api/targets` | `routers/targets.py` | 社交媒体监控目标 CRUD |
| `/api/websites` | `routers/websites.py` | 网站监控目标 CRUD |
| `/api/results` | `routers/results.py` | 监控结果查询 |
| `/api/dashboard` | `routers/dashboard.py` | 仪表盘统计 |
| `/api/schedule` | `routers/schedule.py` | 调度 (jobs, run, start, stop) |
| `/api/settings` | `routers/settings.py` | 系统设置 (AI 提供商、API Key、模型名、提示词) |
| `/api/tools` | `routers/tools.py` | 工具与状态检查 + 图片代理 (`/api/tools/proxy/image`) |
| `/api/hot-topics` | `routers/hot_topics.py` | 热门话题查询、抓取、删除 |
| `/api/hot-topic-sources` | `routers/hot_topics.py` | 热门话题平台源管理 |
| `/api/sentiment` | `routers/sentiment.py` | 舆情搜索、任务管理、平台信息 |

## 爬虫降级链

OpenCLI → CDP → Scrapling → Playwright，通过 `crawlers/router.py:CrawlerRouter` 统一调度。
`build_default_router()` 构建降级链，`get_router()` 返回单例。
`crawl_with_fallback()` 已简化为 router 的薄委托（`services/monitor.py`）。

各爬虫入口通过 `build_*_entry()` 注册，自声明支持的平台：
- **OpenCLI**: `opencli_crawler.py:build_opencli_entry()` — x, xiaohongshu, reddit, bilibili
- **CDP**: `cdp_crawler.py:build_cdp_entry()` — x only
- **Scrapling**: `__init__.py:_build_scrapling_entry()` — toutiao（stealth browser，无需 Chrome CDP）
- **Playwright**: `__init__.py:_build_playwright_entry()` — x, youtube, xiaohongshu, douyin, weibo, toutiao, 108community
- **Claude**: `claude_crawler.py:build_claude_entry()` — 全平台（默认未注册）

每次降级记录原因到 `error_log`，成功时记录 `crawl_method` 到 `MonitorResult`。

## 图文分析

帖子中的图片 URL 会被提取并随文本一起发送给 AI 多模态 API 进行分析。

- **提取**: `crawlers/opencli_crawler.py:_extract_image_urls()` 从 OpenCLI JSON 中提取 `media_urls`、`cover`、`pic` 等字段
- **传递**: 图片 URL 存入 `PostData.images`，经 `monitor.py` 序列化到 `raw_content` JSON 中
- **分析**: `summarizer.py:_call_ai()` 支持多模态 content 数组格式，失败时自动回退纯文本
- **展示**: `MonitorDetailPage.tsx` 用 Ant Design `Image.PreviewGroup` 展示缩略图
- **限制**: 每帖最多 5 张图片，每批次最多 10 张

## 日志

`main.py` 配置了 `logging.basicConfig(level=logging.INFO)`，关键流程均有日志输出：
- 爬虫尝试/成功/失败、图片提取数量
- AI API 请求模式（多模态/纯文本）、耗时、响应状态
- 监控任务开始/完成/异常

## 热门话题 (Hot Topics)

通过 AutoCLI 抓取 16 个平台热门话题，支持按平台筛选、拖拽排序、定时抓取。

- **爬取模式**: `public` 模式平台并发抓取，`browser` 模式平台串行抓取（复用 Chrome CDP 上下文）
- **Playwright 降级**: `browser` 模式平台在 AutoCLI 失败时自动尝试 Playwright headless 抓取（当前已实现微博热搜，`autocli_service.py:_fetch_weibo_hot_via_playwright()`）
- **异步抓取**: `POST /api/hot-topics/fetch` 立即返回 `{"pending": true}`，后台 `asyncio.create_task` 执行，前端每 3 秒轮询刷新
- **平台配色**: 每个平台独立主题色（`PLATFORM_COLORS` map），前端渲染时动态注入卡片、头像、热度标签
- **排名徽章**: 前三名金银铜配色 (`RANK_COLORS`)
- **时间处理**: 后端 `datetime.now(timezone.utc)` 存时区感知 UTC，前端 `formatBeijingTime()` 统一转北京时间

## 舆情监测 (Sentiment Monitoring)

通过关键词在 5 个中文平台（微博、抖音、小红书、今日头条、108天台社区）实时搜索帖子，按综合影响力排序。

- **搜索流程**: `POST /api/sentiment/search` 创建任务 → 后台 `asyncio.create_task` 并发搜索各平台 → 前端每 3s 轮询 `GET /api/sentiment/tasks/{id}` → 完成后展示结果
- **影响力公式**: `engagement_score × platform_weight × time_decay × 100`
  - `engagement_score`: 各互动指标（views/likes/comments/shares/bookmarks）加权平均，权重分别为 0.5/1.0/2.5/3.5/2.0
  - `platform_weight`: `log10(MAU)/log10(max_MAU)` 钳位到 [0.3, 0.7]
  - `time_decay`: `e^(-λ × days_ago)`，半衰期默认 4 天
- **归一化**: 平台内百分位优先（需 ≥1000 样本），冷启动降级为同指标 log10 归一化
- **自适应分母**: 只对平台实际返回的指标加权求平均，`metrics_partial` 标记字段缺失
- **图片代理**: `/api/tools/proxy/image?url=...` 添加 Referer 头绕过微博 CDN 防盗链
- **数据清理**: 30 天前的 sentiment_tasks 和 posts 自动清理（scheduler 每日 4:07 AM 执行）
- **已知限制**:
  - 微博 API 无公开浏览量字段（`views = 0`）
  - 抖音关键词搜索需 Chrome CDP 登录态，搜索交互仍需逆向
  - 今日头条搜索页无需登录即可抓取（Scrapling + stealth browser），用户主页需 real_chrome 继承登录态。108社区搜索 URL 全部返回 500，需 Playwright CDP 辅助搜索。
- **平台 MAU 默认值**: 微博 5.86 亿 / 抖音 7.3 亿 / 小红书 3 亿 / 头条 3.5 亿 / 108社区 50 万

## 红线

- **数据库迁移**：新增模型字段后需手动 `ALTER TABLE` 添加列（无 Alembic）
- **密码存储**：bcrypt hash，绝不明文
- **不要在 routers/ 里写业务逻辑**，用 services/ 层
- **后端新增路由后需全杀 Python 重启**：`reload=True` 模式下 uvicorn 可能遗留旧 worker，新路由不生效时执行 `taskkill /F /IM python.exe` 后重新启动
- **新增爬虫必须设置 `published_at`**：从平台 DOM 或 API 提取发帖时间，统一存为 naive UTC datetime。使用 `crawlers.base` 中的 `parse_relative_time()`（相对时间如"3天前"）或 `parse_absolute_time()`（绝对时间如"2024-06-14"）解析，中文平台默认视为北京时间转 UTC。时间筛选、评分衰减、前端显示都依赖此字段，不设置会导致筛选失效、评分虚高
- **热门话题抓取超时**：前端 axios 默认 30s，批量抓取 12 个平台需 3-5 分钟。`/api/hot-topics/fetch` 已改为异步模式避免超时。如需同步抓取，`api.ts` 中 `triggerFetch` 单独设了 600s 超时
- **AutoCLI 依赖 Chrome**：`browser` 模式平台需要 Chrome 运行且开启 CDP 调试端口，否则抓取失败。微博热搜已内置 Playwright 备选方案，不受此限制
- **微博 pics 字段类型不一致**：`m.weibo.cn` API 返回的 `mblog.pics` 有时是 `list`，有时是 `dict`（key 为数字字符串）。`weibo_crawler.py` 中已用 `isinstance(pics_raw, dict)` 兼容处理
- **舆情搜索图片显示**：微博图片需通过 `/api/tools/proxy/image` 代理，否则 403；前端 `PostImages` 组件自动将 weibo 图片 URL 转为代理 URL
- **舆情搜索数据库迁移**：新增 `images_json`/`videos_json` 列后需重建 SQLite 数据库（无 Alembic）
- **Scrapling 安装**：需 `pip install "scrapling[fetchers]"` + `scrapling install` 安装 Playwright 浏览器依赖。否则 Scrapling entry 可用性检查失败，自动降级到 Playwright
