# Intel Monitor 开发手册

> 社交媒体情报监控平台：FastAPI 后端 + React/Ant Design 前端
> 最后更新：2026-07-13

---

## 快速启动

```bash
cd intel-monitor

# 方式一：一键启动
start.bat                           # 后端 (localhost:8000) + 前端 (localhost:3000)

# 方式二：手动启动
cd backend && python main.py        # 后端：uvicorn，自动 reload
cd frontend && npm run dev          # 前端：Vite dev server，热更新
```

**注意：** 生产模式下，修改前端源码后需 `cd frontend && npm run build` 重建 dist（FastAPI 静态托管）。

---

## 环境与配置

### 运行环境

| 组件 | 版本/路径 |
|------|-----------|
| 系统 | Windows 11 Pro for Workstations |
| Python | 3.14 (`C:\Program Files\Python314\`) |
| Node.js | v24.16.0 |
| 包管理器 | npm、pip |
| 数据库 | SQLite (`backend/data/intel_monitor.db`) |

### 环境变量 (`backend/.env`)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_PROVIDER` | `minimax` | 默认 AI 提供商 (minimax / deepseek / mimo) |
| `MINIMAX_API_KEY` | — | MiniMax API Key |
| `MINIMAX_BASE_URL` | `https://api.minimaxi.com/v1/chat/completions` | MiniMax 端点 |
| `MINIMAX_MODEL` | `MiniMax-M2.7` | MiniMax 模型 |
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek 端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek 模型 |
| `MIMO_API_KEY` | — | MiMo API Key |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | MiMo 端点 |
| `MIMO_MODEL` | `mimo-v2.5-pro` | MiMo 模型 |
| `FIRECRAWL_API_KEY` | — | Firecrawl API Key |
| `TAVILY_API_KEY` | — | Tavily API Key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/intel_monitor.db` | 数据库连接 |
| `JWT_SECRET` | (自动生成) | JWT 密钥，每次重启重置除非写入 .env |
| `JWT_EXPIRE_MINUTES` | `1440` | Token 有效期（24h） |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 监听地址 |
| `SUMMARIZE_POSTS_PROMPT` | (见代码) | 贴文分析 system prompt |
| `SUMMARIZE_WEBSITE_PROMPT` | (见代码) | 网站分析 system prompt |
| `INTELLIGENCE_REPORT_PROMPT` | (见代码) | 情报报告 system prompt |

> 所有 AI 提供商配置（API Key、模型名、system prompt）均可通过前端「系统设置」页面修改。

---

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                    Frontend                      │
│  React 18 / Ant Design 5 / Vite 5 / TypeScript  │
│                 localhost:3000                   │
└────────────────────┬────────────────────────────┘
                     │ /api/* (Vite 代理至 :8000)
┌────────────────────▼────────────────────────────┐
│                    Backend                       │
│       FastAPI + uvicorn (localhost:8000)         │
│  routers/ ──► services/ ──► crawlers/           │
│                       ──► AI (MiniMax/DeepSeek/MiMo) │
│  models/ + SQLAlchemy async (aiosqlite)          │
│  APScheduler 定时任务                            │
└─────────────────────────────────────────────────┘
```

### 第三方服务依赖

| 服务 | 用途 | 必需 |
|------|------|------|
| Chrome CDP (`:9222`) | XHS 搜索 + 热门话题 browser 模式 | 部分功能 |
| CDP Proxy (`:3456`) | XHS CDP 搜索的 Node.js 中间层 | XHS 舆情搜索必需 |
| OpenCLI | 社交媒体账号监控（x、小红书、bilibili 等） | 账号监控 |
| AutoCLI | 热门话题抓取（16 平台） | 热门话题 |
| MiniMax / DeepSeek / MiMo | AI 摘要、情报报告 | 摘要 + 报告 |

### CDP Proxy 说明

CDP Proxy (`node cdp-proxy.mjs`) 是 Node.js HTTP 服务，将 HTTP 请求转为 Chrome DevTools Protocol 命令。启动方式：

1. **自动启动**：XHS 舆情搜索触发 `_ensure_cdp_proxy()` → `subprocess.Popen` 按需启动
2. **手动启动**：`node .claude/skills/web-access/scripts/cdp-proxy.mjs`

脚本路径：`.claude/skills/web-access/scripts/cdp-proxy.mjs`

---

## 数据库

### 表清单

| 表 | 文件 | 说明 |
|---|------|------|
| `users` | `models/user.py` | 用户（username 唯一、bcrypt 密码） |
| `targets` | `models/target.py` | 社交媒体监控目标 |
| `website_targets` | `models/website.py` | 网站监控目标 |
| `monitor_results` | `models/result.py` | 监控结果（含 AI 摘要） |
| `hot_comments` | `models/comment.py` | 热门评论（FK → monitor_results） |
| `hot_topic_sources` | `models/hot_topic_source.py` | 热门话题平台源 |
| `hot_topics` | `models/hot_topic.py` | 热门话题 |
| `sentiment_tasks` | `models/sentiment_task.py` | 舆情搜索任务 |
| `sentiment_posts` | `models/sentiment_post.py` | 舆情搜索结果贴文 |
| `platform_stats` | `models/platform_stats.py` | 平台百分位基线 |
| `intelligence_categories` | `models/intelligence_category.py` | 情报报告分类（树形） |
| `intelligence_reports` | `models/intelligence_report.py` | 情报报告（AI 生成） |

### 数据库迁移

**无 Alembic。** 新增模型字段后需手动 `ALTER TABLE`：

```sql
-- 示例：新增 comments_json 列
ALTER TABLE sentiment_posts ADD COLUMN comments_json TEXT;
```

新表在启动时通过 `Base.metadata.create_all` 自动创建，但现有表不会自动加列。

---

## 功能模块

### 1. 仪表盘 (Dashboard)

- **路由**：`GET /api/dashboard`
- **功能**：活跃目标数、今日结果数、成功率、最近结果预览
- **前端**：`DashboardPage.tsx`，60 秒轮询

### 2. 社交媒体监控 (Social Accounts)

- **路由**：`/api/targets` (CRUD)、`POST /api/schedule/run/{target_id}`
- **爬虫降级链**：OpenCLI → CDP → Scrapling → Playwright
- **注册**：`crawlers/__init__.py:build_default_router()`
- **调度**：APScheduler，支持 cron_表达式 或 简单间隔
- **AI 摘要**：提取热门评论 + AI 多模态分析（最多 10 张图片）
- **爬虫支持矩阵**：

  | 平台 | OpenCLI | CDP | Scrapling | Playwright |
  |------|---------|-----|-----------|------------|
  | x (Twitter) | ✅ | ✅ | — | ✅ |
  | xiaohongshu | ✅ | — | — | ✅ |
  | reddit | ✅ | — | — | — |
  | bilibili | ✅ | — | — | — |
  | toutiao | — | — | ✅ | ✅ |
  | weibo | — | — | — | ✅ |
  | douyin | — | — | — | ✅ |
  | youtube | — | — | — | ✅ |
  | 108community | — | — | — | ✅ |

### 3. 网站监控 (Websites)

- **路由**：`/api/websites` (CRUD)
- **爬虫**：`WebsiteCrawler`（Playwright headless），支持 CSS 选择器
- **摘要**：AI 分析网站内容变化

### 4. 热门话题 (Hot Topics)

- **路由**：`/api/hot-topics`、`/api/hot-topic-sources`
- **抓取**：AutoCLI（Chrome CDP）+ 微博 Playwright 降级
- **模式**：
  - **browser 模式**（weibo、zhihu、bilibili 等）：串行，复用 Chrome CDP 登录态
  - **public 模式**（v2ex、hackernews、reddit 等）：并发
- **前端**：独立浅色毛玻璃主题 + 平台专属配色
- **抓取方式**：异步，立即返回 `{"pending": true}`，前端每 3s 轮询

### 5. 舆情搜索 (Sentiment Monitoring)

- **路由**：`/api/sentiment/search`、`/api/sentiment/tasks`
- **5 个中文平台**：微博、抖音、小红书、今日头条、108天台社区
- **流程**：创建任务 → 后台并发搜索各平台 → 影响力评分 → 存储结果
- **前端**：3s 轮询任务状态，完成展示排序结果

#### 各平台搜索实现

| 平台 | 实现方式 | 降级方案 |
|------|---------|---------|
| 微博 | AutoCLI → Playwright (`WeiboCrawler.search_by_keyword`) | 自动降级 |
| 抖音 | `DouyinCrawler.search_by_keyword`（Playwright） | 无 |
| **小红书** | CDP 浏览器驱动 → 直接导航搜索 URL → 逐条点击详情 | **无降级** |
| 今日头条 | `ToutiaoCrawler.search_by_keyword`（Playwright） | 无 |
| 108社区 | `Tiantai108Crawler.search_by_keyword`（Playwright） | 无 |

#### 小红书搜索详情（2026-07-13 最新）

- **文件**：`backend/crawlers/xhs_cdp_search.py`
- **完整链路**：`sentiment.py:_search_xiaohongshu()` → `xhs_cdp_search.py:search_xhs()`
- **流程**：
  1. 确保 CDP Proxy 运行（未运行则自动启动 `subprocess.Popen`）
  2. 导航到 `https://www.xiaohongshu.com/search_result?keyword=...`
  3. 登录墙检测（"登录后推荐" → 报错）
  4. 提取搜索卡片（`section.note-item` → title、author、likes、url）
  5. 逐条 JS 点击 `.cover` → 等待 3s → 提取正文 + 互动数据 + **热门评论**
  6. 滚动到评论区 → 等待 1.5s 触发懒加载 → 提取 20 条评论（`_EXTRACT_HOT_COMMENTS_JS`）
- **编码注意**：所有 httpx `content=` 参数必须用 `url.encode("utf-8")` 显式编码
- **互动选择器**：限定在 `.buttons.engage-bar-style` 作用域内，避免误取评论区数据
  - 点赞：`.engage-bar-style .like-wrapper .count`
  - 收藏：`.engage-bar-style .collect-wrapper .count`
  - 评论数：`.engage-bar-style .chat-wrapper .count`
- **依赖**：Chrome 已登录小红书 + CDP Proxy 可访问

#### 影响力公式

```
impact_score = engagement_score × platform_weight × time_decay × 100
```

- **engagement_score**：加权平均（views=0.5, likes=1.0, comments=2.5, shares=3.5, bookmarks=2.0），百分位归一化（≥1000 样本）或 log10 降级
- **platform_weight**：`log10(MAU) / log10(max_MAU)` 钳位 [0.3, 0.7]
- **time_decay**：`e^(-λ × days_ago)`，半衰期默认 4 天
- **平台 MAU**：微博 5.86 亿 / 抖音 7.3 亿 / 小红书 3 亿 / 头条 3.5 亿 / 108社区 50 万

#### `sentiment_posts` 特殊字段

- `images_json`：**小红书平台排除**（`if platform != "xiaohongshu"`）
- `comments_json`：**小红书的评论**提取并存入（作者、正文、点赞数），其他平台暂不支持
- `comments`（int）：评论计数

### 6. 情报报告 (Intelligence Reports)

- **路由**：`/api/intelligence`
- **分类**：20 个预设分类（5 一级 + 15 子/孙级），树形结构
- **流程**：搜索（Firecrawl/Tavily + 5 平台爬虫）→ AI 筛选 → 深度爬取 → AI 生成报告
- **导出**：DOCX / PDF

### 7. 系统设置 (Settings)

- **路由**：`/api/settings`
- **功能**：AI 提供商配置（API Key 读写 .env、模型名、测试连接）、System Prompt 自定义

---

## 前端结构

### 页面路由

| 路径 | 文件 | 说明 |
|------|------|------|
| `/login` | `LoginPage.tsx` | 登录 / 首次设置 |
| `/` | `DashboardPage.tsx` | 仪表盘 |
| `/social` | `SocialAccountsPage.tsx` | 社交媒体账号管理 |
| `/websites` | `WebsitesPage.tsx` | 网站监控管理 |
| `/detail/:type/:id` | `MonitorDetailPage.tsx` | 监控结果详情 + 热门评论 |
| `/hot-topics` | `HotTopicsPage.tsx` | 热门话题（独立毛玻璃主题） |
| `/sentiment` | `SentimentPage.tsx` | 舆情搜索 + 结果展示 |
| `/intelligence` | `IntelligenceReportPage.tsx` | 情报报告 |
| `/settings` | `SettingsPage.tsx` | 系统设置 |

### 关键组件

- `AppLayout.tsx`：侧边栏导航（森林绿主题 `#1a2e26`），折叠响应式，AI 提供商标签
- `SentimentPage.tsx` 子组件：
  - `PostContent`：帖子正文（180 字符折叠/展开）
  - `PostImages`：图片预览（80×80 缩略图 + Image.PreviewGroup）
  - `PostComments`：热门评论（可折叠列表，显示作者、点赞数、正文）
  - `ImpactBadge`：影响力分数徽章（金银铜配色）
  - `MetricRow`：互动指标行（点赞/评论/转发/收藏）

### 图片代理

微博图片需通过 `/api/tools/proxy/image` 代理（添加 Referer 头绕过防盗链）。`PostImages` 组件对所有图片使用代理 URL。

---

## 定时任务

| 任务 | 时间 | 文件 |
|------|------|------|
| 监控目标爬取 | 按各目标 cron/interval 配置 | `scheduler.py:refresh_jobs()` |
| 热门话题抓取 | 按各源 cron 配置 | `scheduler.py:refresh_jobs()` |
| 平台统计刷新 | 每天 3:07 AM | `scheduler.py:_refresh_platform_stats` |
| 舆情数据清理 | 每天 4:07 AM | `scheduler.py:_cleanup_old_sentiment_tasks` (>30天) |

---

## AI 摘要机制

`services/summarizer.py` 的 `ContentSummarizer`：

1. 从 `settings.AI_PROVIDER` 读取活跃提供商
2. HTTP POST 到 OpenAI 兼容端点
3. 支持多模态（图片 URL content 数组），失败自动回退纯文本
4. 内容安全拒绝时自动尝试其他提供商（minimax/mimo 间切换）
5. 全部失败则返回截断的原始文本

---

## 红线与注意事项

1. **不使用 Alembic**：新增模型字段需手动 `ALTER TABLE`。代码中已包含 `models/result.py` 和 `models/sentiment_post.py` 的示例注释
2. **密码**：bcrypt hash，绝不明文
3. **不要在 routers/ 写业务逻辑**：用 services/ 层
4. **后端路由不生效**：执行 `taskkill /F /IM python.exe` 全杀重启
5. **新增爬虫必须设置 `published_at`**：用 `parse_relative_time()` / `parse_absolute_time()` 解析
6. **Playwright 爬虫在 Windows 上**：必须通过 `_run_crawler_in_thread()` 启动 ProactorEventLoop
7. **httpx content= 中文 URL**：必须显式 `url.encode("utf-8")`
8. **微博 pics 字段类型**：可能是 list 或 dict，需 `isinstance(pics_raw, dict)` 兼容
9. **小红书搜索无降级方案**：CDP 是唯一路径，CDP Proxy 或 Chrome 不可用则直接失败
10. **JWT_SECRET 不持久**：每次重启重置，建议在 `.env` 中固定
11. **`.env` 文件并发写入**：Settings 页面直接读写 .env，并发请求有竞态风险
12. **热门话题抓取超时**：前端 `triggerFetch` 单独设 600s 超时

---

## 会话改动记录

### 2026-07-13

- **CDP Proxy 自启动**：`xhs_cdp_search.py:_ensure_cdp_proxy()` 检测到 proxy 未运行时自动 `subprocess.Popen` 启动
- **中文关键词编码修复**：`_cdp_new_tab()` 和 `_cdp_navigate()` 的 httpx `content=` 改为 `url.encode("utf-8")`
- **评论提取**：新增 `_EXTRACT_HOT_COMMENTS_JS`，提取 XHS 详情页顶级评论 + 子回复（最多 20 条），存入 `comments_json`
- **互动计数修复**：JS 选择器限定在 `.engage-bar-style` 作用域，comment 改用 `.chat-wrapper`（而非 `.comment-wrapper`）
- **正文展示修复**：前端标题和正文分离展示（标题加粗、正文可折叠）
- **图片去除**：小红书搜索结果不存储也不展示图片
- **前端评论组件**：`PostComments` 可折叠展示热门评论（作者、点赞数、正文）
- **Git 仓库初始化**：`git init` + 首次全量提交

### 2026-06-20（来自 CLAUDE.md）
- Scrapling 集成（今日头条 stealth browser）
- 图文分析（多模态 AI）
- 16 平台热门话题、舆情监测 5 平台
