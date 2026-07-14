# intel-monitor 数据获取技术方案全景

---

## 整体架构（四层）

```
┌─────────────────────────────────────────────────────────┐
│  Layer 4: 业务编排                                        │
│  monitor.py / sentiment.py / autocli_service.py          │
├─────────────────────────────────────────────────────────┤
│  Layer 3: 降级路由                                        │
│  CrawlerRouter: OpenCLI → CDP → Scrapling → Playwright → Claude  │
├─────────────────────────────────────────────────────────┤
│  Layer 2: 平台爬虫（13 个实现）                             │
│  weibo / x / youtube / xiaohongshu / douyin / toutiao    │
│  tiantai108 / opencli / cdp / claude / website /         │
│  toutiao_scrapling / douyin_scrapling                      │
├─────────────────────────────────────────────────────────┤
│  Layer 1: 统一数据结构                                    │
│  PostData / CommentData / CrawlResult                    │
└─────────────────────────────────────────────────────────┘
```

### Layer 1 — 统一数据结构

```python
# CommentData: text, author, likes, url

# PostData: url, title, content
#   互动指标: likes, comments_count, shares, views, bookmarks
#   作者信息: author_name, author_avatar, author_followers
#   时间: published_at (naive UTC datetime)
#   媒体: comments[], images[], videos[]

# CrawlResult: posts[], raw_html, success, error_message
```

所有爬虫的输出统一为 `PostData` 列表，是爬虫层与业务层之间的唯一契约。

### 时间规范化（2026-06-14 实施）

所有 `published_at` 统一存为 **naive UTC datetime**（无时区信息），SQLite 存储兼容。

`crawlers/base.py` 提供两个时间解析工具：
- **`parse_relative_time(text)`**：解析中英文相对时间（"3 days ago"、"2小时前"、"5分钟前"、"1 week ago"、"2个月前"），返回 naive UTC datetime
- **`parse_absolute_time(text, assume_utc=False)`**：解析绝对时间（"2024-06-14 10:30:00"、"06-14"），默认中文平台视为北京时间转 UTC

各平台时间提取情况：

| 平台 | 时间来源 | 解析方式 |
|------|----------|----------|
| 微博 | API `created_at` 字段（`%a %b %d %H:%M:%S %z %Y`） | `%z` 解析 + UTC 转换 |
| X/Twitter | `<time datetime="...">` ISO 8601 属性 | `fromisoformat` + UTC |
| YouTube | `#metadata-line` 第 2 个 span（"3 days ago"） | `parse_relative_time` |
| 抖音 | `span[class*="time"]`（"3天前" / "06-14"） | `parse_relative_time` / `parse_absolute_time` |
| 今日头条 | `span[class*="time"]`（"3小时前"） | `parse_relative_time` / `parse_absolute_time` |
| 108社区 | 论坛时间列（"YYYY-MM-DD HH:MM"） | `parse_absolute_time` |
| 小红书 | 列表页无时间，暂跳过 | — |

### Layer 3 — 降级路由

`CrawlerRouter` 维护一个优先级有序的 `CrawlerEntry` 列表，每个 Entry 声明：
- `name`：标识（如 "opencli"）
- `platforms`：支持的平台集合（frozenset）
- `crawl`：爬取协程函数
- `available`：运行时可用性检查

降级逻辑：依次尝试 → 检查可用 → 执行 → 成功立即返回 / 失败记录 error_log 并尝试下一个。

---

## 三大数据获取场景

| 场景 | 入口 | 平台数 | 核心服务 |
|------|------|--------|----------|
| **社交账号监测** | `monitor.py` → Router 降级链 | 7 个 | 定时执行 → 爬取 → AI 摘要 → 存库 |
| **舆情关键词搜索** | `sentiment.py` | 5 个中文平台 | 并发搜索 → 影响力评分 → 排序展示 |
| **热门话题抓取** | `autocli_service.py` | 16 个平台 | AutoCLI + Playwright 降级 |

---

## 各平台爬虫实现一览

| 平台 | 爬虫文件 | 数据获取方式 | 提取字段 | 降级链覆盖 |
|------|----------|-------------|----------|-----------|
| **微博** | `weibo_crawler.py` | Playwright + m.weibo.cn 移动 API | 全量（likes/comments/shares/images/videos/author/published_at） | OpenCLI ✗ → CDP ✗ → **Playwright ✓** |
| **X/Twitter** | `x_crawler.py` | Playwright DOM 抓取 | content + likes + published_at（无 images/shares/views） | **OpenCLI ✓** → **CDP ✓** → **Playwright ✓** |
| **YouTube** | `youtube_crawler.py` | Playwright DOM 抓取 | title + views 文本 + published_at（无 likes/comments） | OpenCLI ✗ → CDP ✗ → **Playwright ✓** |
| **小红书** | `xiaohongshu_crawler.py` | Playwright DOM 抓取 | title + url（无互动数据、无发布时间） | **OpenCLI ✓** → CDP ✗ → **Playwright ✓** |
| **抖音** | `douyin_crawler.py` | Playwright 连接用户 Chrome CDP | title + url + published_at（无互动数据） | OpenCLI ✗ → CDP ✗ → **Playwright ✓** |
| **今日头条** | `toutiao_crawler.py` | Playwright 连接用户 Chrome CDP | title + content + comments_count + published_at | OpenCLI ✗ → CDP ✗ → **Playwright ✓** |
| **108社区** | `tiantai108_crawler.py` | Playwright headless DOM 抓取 | title + content + comments_count + published_at | OpenCLI ✗ → CDP ✗ → **Playwright ✓** |
| **通用网站** | `website_crawler.py` | Playwright headless | body.innerText | 不经 Router，直接调用 |

---

## 四种数据获取技术路线

### 1. CLI 工具调用（OpenCLI / AutoCLI）

```
前端 → 后端 → subprocess.run(["opencli", "x", "posts", username])
             → JSON stdout → 解析为 PostData
```

- **OpenCLI**：npm 全局包，复用 Chrome 登录态，支持 x/xiaohongshu/reddit/bilibili
- **AutoCLI**：Rust CLI 工具，复用 Chrome CDP，支持 16 个平台热搜
- 优势：工具成熟、维护成本低
- 劣势：依赖 Chrome 扩展连接、90s 超时、无评论提取

### 2. CDP 直连浏览器

```
后端 → HTTP 请求 localhost:3456 (CDP Proxy)
     → 打开新标签页 → 注入 JS → 提取 DOM → 关闭标签页
```

- 仅用于 X/Twitter，通过 web-access skill 的 CDP Proxy
- 优势：可注入任意 JS、支持评论提取
- 劣势：仅覆盖 X、每个帖子开新标签页（资源消耗大）

### 3. Playwright 无头浏览器（主力方案）

```
后端 → _run_crawler_in_thread()
     → ProactorEventLoop 中启动 Playwright
     → Chromium headless → 导航/滚动/DOM 查询 → PostData
```

- 最大覆盖：7 个平台全部支持
- 两种模式：
  - **标准 headless**：weibo / youtube / xiaohongshu / x / tiantai108 / website
  - **连接用户 Chrome**：douyin / toutiao（需 `--remote-debugging-port=9222`）
- 微博特殊：先访问 m.weibo.cn 建立 Cookie，再调用移动端 API（非 DOM 抓取）
- 优势：最可靠、覆盖最广、支持评论提取
- 劣势：速度慢、需要管理浏览器实例、DOM 选择器易失效

### 4. AI Agent 委托（Claude Crawler，默认禁用）

```
后端 → 启动 Claude Code CLI 子进程
     → Claude 使用 web-access skill + CDP 浏览器抓取
     → 写 JSON 文件 → 后端读取
```

- 覆盖 7 个平台（最广），但默认关闭
- 优势：理论上最智能、可自适应页面变化
- 劣势：5 分钟超时、结果不稳定、依赖 Claude Code CLI

---

## 降级链工作流

```
请求爬取平台 X 的数据
  │
  ▼
[OpenCLI] ──available?──→ 否 ──→ 跳过
  │ 是
  ▼
执行 ──success?──→ 是 ──→ 返回结果
  │ 否
  ▼
[CDP] ──available?──→ 否 ──→ 跳过
  │ 是
  ▼
执行 ──success?──→ 是 ──→ 返回结果
  │ 否
  ▼
[Playwright] ──available?──→ 否 ──→ 跳过
  │ 是
  ▼
执行 ──success?──→ 是 ──→ 返回结果
  │ 否
  ▼
返回 (None, error_log)
```

### 各平台降级链覆盖矩阵

| 平台 | OpenCLI | CDP | Scrapling | Playwright | Claude（默认禁用） |
|------|---------|-----|-----------|------------|-------------------|
| x (Twitter) | ✓ | ✓ | ✗ | ✓ | ✓ |
| youtube | ✗ | ✗ | ✗ | ✓ | ✓ |
| xiaohongshu | ✓ | ✗ | ✗ | ✓ | ✓ |
| douyin | ✗ | ✗ | ✗* | ✓ | ✓ |
| weibo | ✗ | ✗ | ✗ | ✓ | ✓ |
| toutiao | ✗ | ✗ | ✓ | ✓ | ✗ |
| 108community | ✗ | ✗ | ✗ | ✓ | ✗ |
| reddit | ✓ | ✗ | ✗ | ✗ | ✓ |
| bilibili | ✓ | ✗ | ✗ | ✗ | ✓ |

---

## 舆情关键词搜索流程

```
POST /api/sentiment/search (keyword, platforms)
  │
  ▼
asyncio.gather(各平台并发搜索)
  │
  ├─ weibo: autocli search → 失败 → WeiboCrawler.search_by_keyword()
  ├─ douyin: DouyinCrawler.search_by_keyword() (需 Chrome CDP)
  ├─ xiaohongshu: opencli search
  ├─ toutiao: ToutiaoCrawler.search_by_keyword() (需 Chrome CDP)
  └─ 108: Tiantai108Crawler.search_by_keyword()
  │
  ▼
scoring.py 计算影响力评分
  score = engagement_score × platform_weight × time_decay × 100
  │
  ├─ engagement_score: 各互动指标加权平均（views×0.5, likes×1.0, comments×2.5, shares×3.5, bookmarks×2.0）
  ├─ platform_weight: log10(MAU)/log10(max_MAU)，钳位 [0.3, 0.7]
  └─ time_decay: e^(-λ × days_ago)，半衰期 4 天
  │
  ▼
存入 SentimentPost 表 → 前端轮询展示
```

### 平台 MAU 默认值

| 平台 | MAU | 权重 |
|------|-----|------|
| 抖音 | 7.3 亿 | 0.70 |
| 微博 | 5.86 亿 | 0.66 |
| 今日头条 | 3.5 亿 | 0.61 |
| 小红书 | 3 亿 | 0.59 |
| 108社区 | 50 万 | 0.30 |

---

## 热门话题抓取流程

```
POST /api/hot-topics/fetch (异步，立即返回 pending)
  │
  ▼
fetch_multiple(platforms)
  │
  ├─ browser 模式（weibo/zhihu/bilibili/twitter/douban/xueqiu）：
  │  串行执行 autocli → 失败 → Playwright 降级（仅微博已实现）
  │
  └─ public 模式（v2ex/hackernews/reddit/linux-do/bbc/...）：
     并发执行 autocli
  │
  ├─ github 特殊：httpx 直接抓取 github.com/trending + BeautifulSoup 解析
  │
  ▼
TopicItem 列表 → 存入 HotTopic 表 → 前端 3s 轮询
```

### 16 平台模式分类

| 模式 | 平台 | 特点 |
|------|------|------|
| **browser** | weibo, zhihu, bilibili, twitter, douban_movie, douban_book, xueqiu | 需要 Chrome 登录态，串行执行 |
| **public** | v2ex, hackernews, reddit, linux-do, bbc, google_trends, stackoverflow, github | 无需登录，并发执行 |

---

## 关键痛点

| 痛点 | 影响范围 | 当前状态 |
|------|----------|----------|
| 抖音/头条需用户 Chrome CDP 登录态 | 舆情搜索 | 框架就绪，交互不稳定 |
| YouTube/小红书 DOM 选择器脆弱 | 账号监测 | YouTube 已提取时间，小红书仍无互动数据和时间 |
| X/Twitter 登录墙 + DOM 频繁变化 | 账号监测 + 舆情 | 已提取 content + likes + published_at |
| 微博无公开浏览量 | 舆情评分 | views 始终为 0 |
| AutoCLI 依赖 Chrome 扩展连接 | 热门话题 | 微博已有 Playwright 降级，其他平台无 |
| 108社区搜索 URL 模式猜测 | 舆情搜索 | 未充分测试 |

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `crawlers/base.py` | 数据结构（PostData/CommentData/CrawlResult）+ PlaywrightCrawler 基类 |
| `crawlers/router.py` | CrawlerEntry + CrawlerRouter 降级路由 |
| `crawlers/__init__.py` | build_default_router() 注册降级链 |
| `crawlers/weibo_crawler.py` | 微博：Playwright + 移动 API |
| `crawlers/x_crawler.py` | X/Twitter：Playwright DOM 抓取 |
| `crawlers/youtube_crawler.py` | YouTube：Playwright DOM 抓取 |
| `crawlers/xiaohongshu_crawler.py` | 小红书：Playwright DOM 抓取 |
| `crawlers/douyin_crawler.py` | 抖音：Playwright 连接用户 Chrome |
| `crawlers/toutiao_crawler.py` | 今日头条：Playwright 连接用户 Chrome |
| `crawlers/tiantai108_crawler.py` | 108社区：Playwright headless |
| `crawlers/opencli_crawler.py` | OpenCLI CLI 子进程调用 |
| `crawlers/cdp_crawler.py` | CDP Proxy API 直连 |
| `crawlers/claude_crawler.py` | Claude Code CLI 委托（默认禁用） |
| `crawlers/website_crawler.py` | 通用网站：Playwright headless |
| `services/monitor.py` | 社交账号监测编排 |
| `services/sentiment.py` | 舆情关键词搜索编排 |
| `services/scoring.py` | 影响力评分引擎 |
| `services/autocli_service.py` | 热门话题 AutoCLI 抓取 |
| `services/summarizer.py` | AI 摘要生成 |

---

*最后更新：2026-06-20*
