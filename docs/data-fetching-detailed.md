# intel-monitor 数据获取技术方案详解

> 社交媒体情报监控平台 — 数据获取全链路技术文档
>
> 最后更新：2026-06-20

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [Layer 1：统一数据结构](#2-layer-1统一数据结构)
3. [Layer 2：平台爬虫实现](#3-layer-2平台爬虫实现)
4. [Layer 3：降级路由机制](#4-layer-3降级路由机制)
5. [Layer 4：业务编排层](#5-layer-4业务编排层)
6. [五大技术路线详解](#6-五大技术路线详解)
7. [三大业务场景](#7-三大业务场景)
8. [舆情影响力评分体系](#8-舆情影响力评分体系)
9. [时间规范化方案](#9-时间规范化方案)
10. [关键技术细节](#10-关键技术细节)
11. [当前痛点与改进方向](#11-当前痛点与改进方向)
12. [文件清单](#12-文件清单)

---

## 1. 整体架构概览

系统采用四层架构，从底层数据结构到顶层业务编排，层层递进：

```
┌──────────────────────────────────────────────────────────┐
│  Layer 4: 业务编排                                         │
│  monitor.py / sentiment.py / autocli_service.py           │
│  职责：定时调度、并发控制、AI 摘要、评分排序、结果持久化      │
├──────────────────────────────────────────────────────────┤
│  Layer 3: 降级路由                                         │
│  CrawlerRouter: OpenCLI → CDP → Scrapling → Playwright → Claude │
│  职责：按优先级依次尝试，失败自动降级，记录 error_log       │
├──────────────────────────────────────────────────────────┤
│  Layer 2: 平台爬虫（13 个实现）                             │
│  weibo / x / youtube / xiaohongshu / douyin / toutiao     │
│  tiantai108 / opencli / cdp / claude / website /          │
│  toutiao_scrapling / douyin_scrapling                     │
│  职责：对接各平台 API/DOM，提取结构化数据                    │
├──────────────────────────────────────────────────────────┤
│  Layer 1: 统一数据结构                                      │
│  PostData / CommentData / CrawlResult                     │
│  职责：所有爬虫输出的唯一契约                                │
└──────────────────────────────────────────────────────────┘
```

### 设计原则

1. **统一契约**：所有爬虫无论底层技术（CLI / CDP / Playwright / AI），输出统一为 `PostData` 列表
2. **优雅降级**：每个平台有多条获取路径，主路径失败后自动切换备选
3. **关注点分离**：路由（选哪个）与爬取（怎么爬）解耦，新增爬虫只需注册 `CrawlerEntry`
4. **并发安全**：Playwright 爬虫通过 `ProactorEventLoop` 线程池隔离；Scrapling 爬虫通过 `asyncio.to_thread` 包装，避免 Windows 事件循环冲突

---

## 2. Layer 1：统一数据结构

位于 `crawlers/base.py`，定义了爬虫层与业务层之间的唯一数据契约。

### 2.1 PostData — 帖子数据

```python
@dataclass
class PostData:
    # ── 核心内容 ──
    url: str                          # 帖子链接
    title: str = ""                   # 标题
    content: str = ""                 # 正文

    # ── 互动指标 ──
    likes: int = 0                    # 点赞数
    comments_count: int = 0           # 评论数
    shares: int = 0                   # 分享/转发数
    views: int = 0                    # 浏览/播放数
    bookmarks: int = 0                # 收藏数

    # ── 作者信息 ──
    author_name: str = ""             # 作者昵称
    author_avatar: str = ""           # 作者头像 URL
    author_followers: int = 0         # 作者粉丝数

    # ── 时间 ──
    published_at: datetime | None     # 发帖时间 (naive UTC)

    # ── 媒体 ──
    comments: list[CommentData]       # 热门评论
    images: list[str]                 # 图片 URL 列表
    videos: list[dict]                # 视频信息
```

### 2.2 CommentData — 评论数据

```python
@dataclass
class CommentData:
    text: str                         # 评论文本
    author: str                       # 评论者昵称
    likes: int = 0                    # 评论点赞数
    url: str = ""                     # 评论链接
```

### 2.3 CrawlResult — 爬取结果

```python
@dataclass
class CrawlResult:
    posts: list[PostData]             # 帖子列表
    raw_html: str = ""                # 原始 HTML（调试用）
    success: bool = True              # 是否成功
    error_message: str = ""           # 失败原因
```

### 2.4 重要工具函数

**时间解析**（详见第 9 节）：

| 函数 | 用途 | 示例输入 |
|------|------|----------|
| `parse_relative_time(text)` | 解析相对时间（中/英文） | `"3天前"`, `"2 hours ago"` |
| `parse_absolute_time(text, assume_utc=False)` | 解析绝对时间，中文平台默认北京时间转 UTC | `"2024-06-14 10:30:00"`, `"06-14"` |
| `filter_posts(posts, post_limit, time_range_days)` | 按时间范围过滤帖子 | `time_range_days=7` 排除 7 天前帖子 |

**线程隔离**：

```python
async def _run_crawler_in_thread(coro):
    """Windows 上用 ProactorEventLoop 在独立线程中运行 Playwright 协程"""
```

此函数解决了 Windows Python 3.14 下 `SelectorEventLoop` 不支持子进程的问题。所有 Playwright 爬虫调用都通过此函数包装。

---

## 3. Layer 2：平台爬虫实现

系统共有 13 个爬虫实现，按技术路线分为五类：

### 3.1 Playwright 爬虫（7 个 — 主力方案）

所有 Playwright 爬虫继承自 `PlaywrightCrawler` 基类，提供 `init_browser()` / `close()` 生命周期管理和 `crawl()` / `get_hot_comments()` 抽象方法。

#### 3.1.1 微博 (`weibo_crawler.py`)

**技术方案**：Playwright headless 访问 `m.weibo.cn` 建立 Cookie → 调用移动端 API（非 DOM 抓取）

**实现细节**：
1. 从 URL 中正则提取 UID（支持 `weibo.com/u/xxx`、`weibo.com/xxx`、`m.weibo.cn/u/xxx` 三种格式）
2. 访问 `m.weibo.cn` 首页建立 Cookie（`wait_until="domcontentloaded"` + 3s 等待，避免 networkidle 因长连接永不触发）
3. 通过 `page.evaluate()` 在浏览器上下文中调用两个 API：
   - `container/getIndex?type=uid&value={uid}` — 获取用户信息
   - `container/getIndex?type=uid&value={uid}&containerid=107603{uid}` — 获取帖子列表
4. 从 API 返回的 `cards[].mblog` 中提取字段

**提取字段**：全量

| 字段 | 来源 | 备注 |
|------|------|------|
| `content` | `mblog.text`（HTML） | 经 `_clean_html()` 处理：去 script/iframe、img alt→emoji、HTML→纯文本 |
| `likes` | `mblog.attitudes_count` | |
| `comments_count` | `mblog.comments_count` | |
| `shares` | `mblog.reposts_count` | |
| `author_name` | `mblog.user.screen_name` | |
| `author_avatar` | `mblog.user.profile_image_url` | |
| `author_followers` | `mblog.user.followers_count` | |
| `published_at` | `mblog.created_at` | `"%a %b %d %H:%M:%S %z %Y"` → UTC 转换 |
| `images` | `mblog.pics[].large.url` | pics 可能是 list 或 dict（兼容处理） |
| `videos` | `mblog.page_info.page_url` | `object_type == "11"` 时提取 |

**特殊处理**：
- `mblog.pics` 字段类型不一致：有时是 `list`，有时是 `dict`（key 为数字字符串），已用 `isinstance(pics_raw, dict)` 兼容
- 数值解析支持"万"单位（`1.5万 → 15000`）

**关键词搜索** (`search_by_keyword`)：
- 调用 API `container/getIndex?containerid=100103type%3D60%26q%3D{keyword}&page={page}`
- 最多翻 10 页，与 `crawl()` 共享相同的字段提取逻辑
- 舆情搜索入口优先使用 AutoCLI（`search_weibo_via_autocli`），失败后降级到此方法

#### 3.1.2 X/Twitter (`x_crawler.py`)

**技术方案**：Playwright headless DOM 抓取

**实现细节**：
1. 访问用户主页 → 检测登录墙（`"Log in" in content`）
2. 滚动 3 次加载更多推文 → `query_selector_all('article[data-testid="tweet"]')`
3. 每个 article 内提取子元素
4. 评论通过访问帖子详情页单独抓取

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `content` | `[data-testid="tweetText"]` innerHTML | 保留 emoji img 标签 |
| `likes` | `[data-testid="like"] span` | 支持 K/M 单位 |
| `published_at` | `<time datetime="...">` 属性 | ISO 8601 → UTC 转换 |
| `comments` | 详情页 `article[data-testid="tweet"]` | 跳过第 1 个（主帖本身），按点赞排序取 top 10 |

**未提取**：`shares`、`views`、`images`、`author_name`、`author_avatar`

#### 3.1.3 YouTube (`youtube_crawler.py`)

**技术方案**：Playwright headless DOM 抓取

**实现细节**：
1. 访问频道 `/videos` 页面 → `wait_until="networkidle"`
2. 滚动 2 次加载更多 → `query_selector_all("ytd-rich-item-renderer")`
3. 提取视频标题、链接、观看量、发布时间

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `title` | `#video-title` innerText | |
| `url` | `#video-title` href | 拼接 `https://www.youtube.com` |
| `content` | `#metadata-line span`（第 1 个） | 存入 views 文本 |
| `published_at` | `#metadata-line span`（第 2 个，含 "ago"） | `parse_relative_time()` 解析 |

**未提取**：`likes`、`comments_count`（列表页不可用）

#### 3.1.4 小红书 (`xiaohongshu_crawler.py`)

**技术方案**：Playwright headless DOM 抓取

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `title` | `.title` / `.note-title` / `span` | |
| `url` | `section.note-item` href 属性 | 拼接 `https://www.xiaohongshu.com` |

**已知限制**：列表页无互动数据、无发布时间、无作者信息。评论提取尝试 `.comment-item` / `div[class*="comment"]` 等选择器。

#### 3.1.5 抖音 (`douyin_crawler.py`)

**技术方案**：Playwright **连接用户 Chrome**（`connect_over_cdp`），复用登录态

**与标准 headless 的关键区别**：
- `init_browser()` 通过 CDP（`http://localhost:9222`）连接用户正在运行的 Chrome
- 复用现有浏览器上下文（context）的第一个页面，保留完整登录会话
- `close()` **不关闭浏览器**，只关闭 page 和 playwright 实例

**账号监测抓取**：
1. 访问用户主页 → 滚动 3 次
2. 选择器：`li[class*="item"]` / `div[class*="video-card"]` / `a[href*="/video/"]`
3. 提取标题、链接、时间

**关键词搜索** (`search_by_keyword`)：
1. 先访问抖音首页建立会话
2. 导航至 `https://www.douyin.com/search/{keyword}`
3. 滚动 5 次 → 注入 JS 遍历所有 `a[href]`，筛选 `/video/`、`/user/`、`/note/` 链接
4. 如果 JS 提取结果为空，回退到遍历 `div` 元素

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `title` | `p` / `.title` / `span[class*="title"]` | |
| `url` | 元素 href 属性 | |
| `published_at` | `span[class*="time"]` | `parse_relative_time()` 或 `parse_absolute_time()` |

**未提取**：互动数据（likes/comments/shares/views）

**已知限制**：搜索交互不稳定，DOM 选择器需逆向工程。

#### 3.1.6 今日头条 (`toutiao_crawler.py`)

**技术方案**：Playwright **连接用户 Chrome**（同抖音模式）

**账号监测抓取**：访问用户主页 → 调用 `_parse_search_results()`

**关键词搜索**：
1. 导航至 `https://so.toutiao.com/search?keyword={keyword}`
2. 滚动 3 次
3. 调用 `_parse_search_results()`

**_parse_search_results 通用提取逻辑**：
1. 尝试 6 种选择器 `.search-result-item` / `.result-item` / `div[class*="result"]` / `.article-item` / `div[class*="article"]` / `a[href*="/a"]`
2. 对每个元素提取标题、链接、评论数、作者、时间

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `title` | `a[class*="title"]` / `.title` / `h3` / `h2` | |
| `url` | 标题链接 href 或元素 href | |
| `comments_count` | `[class*="comment"]` / `.comment-count` | |
| `author_name` | `[class*="source"]` / `.author` / `.source` | |
| `published_at` | `span[class*="time"]` / `.time` / `.date` | `parse_relative_time()` 或 `parse_absolute_time()` |

**未提取**：`likes`、`shares`、`views`（搜索结果页不显示）

#### 3.1.7 108天台社区 (`tiantai108_crawler.py`)

**技术方案**：Playwright headless DOM 抓取

**关键词搜索策略**：两阶段尝试
1. **策略一**：直接尝试 4 种搜索 URL 模式（`/search?keyword=`、`/search?q=`、`/search/`、`/search?key=`），检查页面内容是否含有关键词
2. **策略二（CDP 辅助搜索）**：访问首页 → 点击搜索图标 → 填写关键词 → Enter 提交

**_parse_post_list 通用提取**：
1. 尝试 6 种帖子选择器 → 对每个元素提取字段
2. 时间提取尝试 5 种选择器，验证是否含数字

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `title` | `a` / `.title` / `.subject` / `h3` / `h4` | |
| `url` | href 属性，自动补全 `BASE_URL` | |
| `comments_count` | `span:last-child` / `.reply-count` / `.comment-count` | |
| `author_name` | `.author` / `.poster` / `span[class*="user"]` | |
| `published_at` | `td:last-child` / `.time` / `.date` | `parse_absolute_time()` |

**未提取**：`likes`、`shares`、`views`（论坛无这些指标）

#### 3.1.8 通用网站 (`website_crawler.py`)

**技术方案**：Playwright headless，提取页面正文

**特点**：不经过 Router 降级链，由 `monitor.py` 直接调用

```python
# 支持 CSS 选择器指定目标区域
content = await page.inner_text(css_selector or "body")
# 限制 5000 字符
```

### 3.2 CLI 工具爬虫 (`opencli_crawler.py`)

**技术方案**：通过 `subprocess.run` 调用 OpenCLI CLI 工具

**平台命令映射**：

| 平台 | OpenCLI 命令 | 参数 |
|------|-------------|------|
| X/Twitter | `opencli twitter tweets {username} --limit N --format json` | 用户名从 URL 提取 |
| 小红书 | `opencli xiaohongshu search {keyword} --limit N --format json` | 直接使用 account_name |
| Reddit | `opencli reddit hot --limit N --format json` | |
| Bilibili | `opencli bilibili hot --limit N --format json` | |

**实现细节**：
1. Windows 上通过 `asyncio.to_thread` 包装 `subprocess.run`，避免 `asyncio.create_subprocess_exec` 在 `SelectorEventLoop` 下的 `NotImplementedError`
2. 90 秒超时，最多重试 3 次（含 2s 间隔）
3. 自动从 stdout 中定位 JSON 起始位置（`[` 或 `{`）
4. 各平台有独立的 JSON 解析器：`_parse_twitter_posts` / `_parse_xiaohongshu_posts` / `_parse_reddit_posts` / `_parse_bilibili_posts`

**图片提取** (`_extract_image_urls`)：
- 尝试多种字段名：`media` / `media_urls` / `photos` / `images` / `image_list`
- 额外尝试 `cover`（小红书）、`pic`（Bilibili）
- 最多 5 张

**数值解析** (`_parse_count`)：
- 支持 K/M 单位（英文）、万单位（中文）

### 3.3 CDP 爬虫 (`cdp_crawler.py`)

**技术方案**：通过 HTTP 请求 `localhost:3456`（CDP Proxy）控制浏览器

**CDP Proxy API**：

| 端点 | 方法 | 作用 |
|------|------|------|
| `/targets` | GET | 检查代理是否运行 |
| `/new?url=...` | GET | 创建新标签页，返回 targetId |
| `/eval?target=...` | POST | 执行 JavaScript，返回结果 |
| `/scroll?target=...&y=...` | GET | 滚动页面 |
| `/close?target=...` | GET | 关闭标签页 |

**X/Twitter 爬取流程**：
1. 创建标签页 → 等待 5s → 检查登录墙
2. 滚动 3 次（每次 800px, 间隔 2s）
3. 注入 `X_EXTRACT_POSTS_JS` 提取帖子（innerHTML + 链接 + 点赞）
4. 对每条帖子：开新标签页 → 等待 4s → 滚动 → 注入 `X_EXTRACT_COMMENTS_JS` → 提取评论
5. 关闭所有标签页

**提取字段**：

| 字段 | 来源 | 备注 |
|------|------|------|
| `content` | `[data-testid="tweetText"]` innerHTML | 清理 on* 事件处理 |
| `url` | `a[href*="/status/"]` | |
| `likes` | `[data-testid="like"] span` | 支持 K/M 单位 |
| `comments` | 详情页 tweet articles（跳过第 1 个） | 按点赞排序取 top 10 |

**通用网站爬取**：注入 `WEBSITE_EXTRACT_JS`，支持 CSS 选择器，限制 5000 字符。

### 3.4 Claude AI Agent 爬虫 (`claude_crawler.py`)

**技术方案**：启动 Claude Code CLI 子进程，利用 `web-access` skill + CDP 浏览器抓取

**流程**：
1. 将爬取任务描述（URL、输出格式）写入 prompt 文件
2. 启动 `claude -p {prompt_content}` 子进程
3. 等待结果 JSON 文件出现（最多 5 分钟，每 5s 轮询）
4. 解析 JSON 结果 → `CrawlResult`

**两种模式**：
- `crawl_with_claude`：新窗口启动 PowerShell，异步等待
- `crawl_with_claude_sync`：直接等待进程完成（用于 Router 注册）

**覆盖平台**（最广）：x, xiaohongshu, reddit, bilibili, youtube, weibo, douyin

**当前状态**：默认未注册到 Router（需手动启用）

### 3.5 爬虫注册与 Router 组装

`build_default_router()` 在 `crawlers/__init__.py` 中组装降级链：

```python
def build_default_router() -> CrawlerRouter:
    return CrawlerRouter([
        build_opencli_entry(),     # 第 1 优先级：x, xiaohongshu, reddit, bilibili
        build_cdp_entry(),         # 第 2 优先级：x only
        _build_playwright_entry(), # 第 3 优先级：全部 7 个平台
        # build_claude_entry(),    # 第 4 优先级：默认未启用
    ])
```

`CRAWLER_MAP` 维护 Playwright 爬虫的平台-类映射：

```python
CRAWLER_MAP = {
    "x": XCrawler, "youtube": YouTubeCrawler,
    "xiaohongshu": XiaoHongShuCrawler, "douyin": DouyinCrawler,
    "weibo": WeiboCrawler, "toutiao": ToutiaoCrawler,
    "108community": Tiantai108Crawler,
}
```

---

## 4. Layer 3：降级路由机制

### 4.1 核心数据结构

```python
@dataclass
class CrawlerEntry:
    name: str                                    # 标识 (如 "opencli")
    platforms: frozenset[str]                    # 支持的平台集合
    crawl: Callable[..., Coroutine]              # 爬取协程
    available: Callable[[], Coroutine[bool]]     # 运行时可用性检查
```

每个 Entry 自声明其能力和可用性，Router 不关心内部实现。

### 4.2 降级流程

```
请求爬取平台 X 的数据
  │
  ▼
遍历 Router 中每个 Entry (按注册顺序):
  │
  ├─ platform 不在 platforms 中? ──→ 跳过
  │
  ├─ available() 返回 False? ──→ 记录 "not available"，跳过
  │
  ├─ 执行 crawl() ──→ success? ──→ 返回 (result, method_name, error_log)
  │  │ 否
  │  └─ 记录失败原因，继续下一个
  │
  ▼
所有 Entry 都失败 → 返回 (None, "none", error_log)
```

### 4.3 各平台降级链覆盖矩阵

| 平台 | OpenCLI | CDP | Playwright | Claude（默认禁用） |
|------|---------|-----|------------|-------------------|
| **x (Twitter)** | ✓ | ✓ | ✓ | ✓ |
| **youtube** | ✗ | ✗ | ✓ | ✓ |
| **xiaohongshu** | ✓ | ✗ | ✓ | ✓ |
| **douyin** | ✗ | ✗ | ✓ | ✓ |
| **weibo** | ✗ | ✗ | ✓ | ✓ |
| **toutiao** | ✗ | ✗ | ✓ | ✗ |
| **108community** | ✗ | ✗ | ✓ | ✗ |
| **reddit** | ✓ | ✗ | ✗ | ✓ |
| **bilibili** | ✓ | ✗ | ✗ | ✓ |

### 4.4 可用性检查机制

| Entry | 检查方式 |
|-------|----------|
| OpenCLI | `shutil.which("opencli") is not None` |
| CDP | HTTP GET `localhost:3456/targets` → 200 |
| Playwright | `from playwright.async_api import async_playwright` 导入成功 |
| Claude | `shutil.which("claude") is not None` |

### 4.5 Router 设计优势

1. **声明式注册**：每个爬虫自声明平台覆盖，添加新爬虫只需 `router.register(entry)`
2. **统一错误追踪**：每次降级记录原因到 `error_log`，最终一并返回供上层分析
3. **成功方法追踪**：返回实际使用的 `method_name`，存入 `MonitorResult.crawl_method` 用于统计和调试
4. **运行时检查**：`available()` 每次调用时重新检查（而非注册时一次性），支持工具动态安装/卸载

---

## 5. Layer 4：业务编排层

### 5.1 社交账号监测 (`services/monitor.py`)

**职责**：定时执行监测任务 → 爬取目标账号 → AI 摘要 → 存入 `MonitorResult`

**流程**：
1. APScheduler 触发 → 加载所有活跃的 `Target`
2. 对每个 Target：调用 `get_router().crawl(platform, account_name, account_url)`
3. 获取帖子列表 → 调用 AI 摘要（`summarizer.py`）
4. 存入 `MonitorResult`（包含 `raw_content` JSON、`summary`、`crawl_method`）

**串行化**：`raw_content` 存入时序列化 `published_at.isoformat()`

### 5.2 舆情关键词搜索 (`services/sentiment.py`)

**职责**：接收关键词和平台列表 → 并发搜索 → 影响力评分 → 排序展示

**流程**：
1. `POST /api/sentiment/search` 创建 `SentimentTask`（status=pending）
2. 后台 `asyncio.create_task` 执行 `run_sentiment_search()`
3. 5 个平台 `asyncio.gather` 并发搜索
4. 各平台搜索策略：

| 平台 | 搜索入口 | 降级方案 |
|------|----------|----------|
| 微博 | AutoCLI (`search_weibo_via_autocli`) | Playwright (`WeiboCrawler.search_by_keyword`) |
| 抖音 | `DouyinCrawler.search_by_keyword()` (需 CDP) | — |
| 小红书 | `crawl_with_opencli("xiaohongshu", keyword)` | — |
| 今日头条 | `ToutiaoCrawler.search_by_keyword()` (需 CDP) | — |
| 108社区 | `Tiantai108Crawler.search_by_keyword()` | — |

5. 结果存入 `SentimentPost` 表
6. 调用 `scoring.calculate_impact()` 计算每条帖子影响力
7. 任务状态更新为 completed
8. 前端每 3s 轮询 `GET /api/sentiment/tasks/{id}`

**并发控制**：`asyncio.gather(*platform_tasks)` 一次性等待所有平台结果，单个平台失败不影响其他。

### 5.3 热门话题抓取 (`services/autocli_service.py`)

**职责**：通过 AutoCLI 抓取 16 个平台热搜

**流程**：
1. `POST /api/hot-topics/fetch` 立即返回 `{"pending": true}`
2. 后台异步执行 `fetch_multiple(platforms)`
3. 按模式分流：

```
browser 模式（串行）：weibo / zhihu / bilibili / twitter / douban_movie / douban_book / xueqiu
  └─ autocli {site} {command} → 失败 → Playwright 降级（仅微博已实现）

public 模式（并发）：v2ex / hackernews / reddit / linux-do / bbc / google_trends / stackoverflow
  └─ autocli {site} {command}

GitHub 特殊：httpx 直接抓取 github.com/trending + BeautifulSoup 解析
```

4. 结果归一化为 `TopicItem`（title / url / rank / hot_value / extra）
5. 存入 `HotTopic` 表
6. 前端每 3s 轮询刷新

**模式分类原因**：
- `browser` 模式平台需要 Chrome 登录态，AutoCLI 复用同一个浏览器上下文，并发会导致冲突
- `public` 模式平台无需登录，可以并发加速

**微博热搜 Playwright 降级**（唯一已实现的 browser 降级）：
- 访问 `m.weibo.cn` 建立 Cookie
- 调用 API `container/getIndex?containerid=106003type%3D25%26t%3D3%26disable_hot%3D1%26filter_type%3Drealtimehot`
- 从 `cards[].card_group[]` 中提取热搜条目
- 自动去重

---

## 6. 五大技术路线详解

### 6.1 CLI 工具调用 (OpenCLI / AutoCLI)

```
前端 → 后端 → subprocess.run(["opencli", "x", "posts", username])
             → JSON stdout → 解析为 PostData
```

**OpenCLI**（npm 全局包）：
- 定位：账号监测的**第一优先级**方案
- 覆盖：x / xiaohongshu / reddit / bilibili
- 原理：复用 Chrome 扩展连接的浏览器登录态，无需额外凭据
- 输出：JSON（`--format json`）
- 执行：`subprocess.run` + `asyncio.to_thread`（90s 超时，3 次重试）

**AutoCLI**（Rust 单二进制，4.7MB）：
- 定位：热门话题的**主力方案**
- 覆盖：16 个平台热搜
- 原理：同 OpenCLI，复用 Chrome CDP 登录态
- 模式：`browser`（需 Chrome，串行）vs `public`（无需登录，并发）

**优势**：
- 工具成熟，社区维护，跟随平台变化自动更新
- 零凭据管理（复用用户浏览器登录状态）
- 输出稳定（固定 JSON 格式）

**劣势**：
- 依赖 Chrome 扩展连接（AutoCLI 需要，OpenCLI 也建议）
- 90s 超时限制
- 不提取评论
- 不支持所有平台（如 YouTube、抖音）

### 6.2 CDP 直连浏览器

```
后端 → HTTP 请求 localhost:3456 (CDP Proxy)
     → 打开新标签页 → 注入 JS → 提取 DOM → 关闭标签页
```

**定位**：X/Twitter 的第二优先级方案

**CDP Proxy**：由 `web-access` skill 提供，监听 `localhost:3456`

**API**：`/new`（开标签）→ `/eval`（执行 JS）→ `/scroll`（滚动）→ `/close`（关标签）

**优势**：
- 可注入任意 JavaScript（比 Playwright 更底层）
- 支持评论提取（每个帖子开新标签页访问详情页）
- 复用用户 Chrome 登录态

**劣势**：
- 仅覆盖 X/Twitter（因为每平台需要单独编写 JS 提取脚本）
- 每个帖子开新标签页 → 资源消耗大（10 个帖子 = 最多 11 个标签页）
- 依赖 CDP Proxy 运行
- JavaScript 提取脚本需维护（DOM 变化时更新 `X_EXTRACT_POSTS_JS` / `X_EXTRACT_COMMENTS_JS`）

### 6.3 Playwright 无头浏览器（主力方案）

```
后端 → _run_crawler_in_thread()
     → ProactorEventLoop 中启动 Playwright
     → Chromium headless → 导航/滚动/DOM 查询 → PostData
```

**定位**：最大覆盖的**兜底方案**（7 个平台全部支持）

**两种运行模式**：

| 模式 | 平台 | 实现方式 |
|------|------|----------|
| **标准 headless** | weibo / youtube / xiaohongshu / x / tiantai108 / website | `chromium.launch(headless=True)` |
| **连接用户 Chrome** | douyin / toutiao | `chromium.connect_over_cdp("http://localhost:9222")` |

**Windows 线程隔离** (`_run_crawler_in_thread`)：

```python
async def _run_crawler_in_thread(coro):
    if sys.platform == "win32":
        # 在独立线程中创建 ProactorEventLoop 运行 Playwright
        # 解决 SelectorEventLoop 不支持子进程的问题
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return await loop.run_in_executor(pool, _run_in_proactor)
    return await coro
```

**优势**：
- 最可靠、覆盖最广
- 支持评论提取（weibo 热评 API、X 回复、YouTube 评论区）
- 微博使用 API 而非 DOM（更稳定）
- 支持连接用户 Chrome（抖音/头条复用登录态）

**劣势**：
- 速度慢（启动浏览器 + 页面加载 + 滚动等待）
- DOM 选择器易因平台改版失效
- 需要管理浏览器实例生命周期
- 抖音/头条需要用户额外启动 Chrome（`--remote-debugging-port=9222`）

### 6.4 Scrapling Stealth Browser（2026-06-20 新增）

```
后端 → asyncio.to_thread()
     → Scrapling StealthyFetcher.fetch()
     → 隐身 Chromium → 导航/滚动/JS 注入 → PostData
```

**定位**：适用于**不需要登录**或**需继承用户 Chrome 登录态**的公开平台

**流程**：
1. `StealthyFetcher.fetch(url, headless=True, solve_cloudflare=True)` 启动隐身浏览器
2. 内置 TLS 指纹伪装 + Cloudflare Turnstile 绕过 + 广告/追踪域名拦截
3. 通过 `page_action` 回调注入 JS 提取 DOM 数据
4. 返回 `Response` 对象 → `CrawlResult`

**两种模式**：

| 模式 | 适用场景 | 实现方式 |
|------|----------|----------|
| 隐身 headless | 搜索页、首页 feed（无需登录） | `headless=True` |
| 真实 Chrome | 用户主页（需登录态） | `real_chrome=True`，启动用户已安装的 Chrome |

**已覆盖平台**：

| 平台 | 页面类型 | 模式 | 状态 |
|------|----------|------|:--:|
| 今日头条 | 搜索页 (`so.toutiao.com`) | headless | ✅ |
| 今日头条 | 首页 feed | headless | ✅ |
| 今日头条 | 用户主页 (`c/user/token/...`) | real_chrome | ✅ |
| 抖音 | 搜索页 | headless | ❌ 需登录 |
| 抖音 | 用户页 | real_chrome | ❌ 需逆向 SPA |

**今日头条实现细节**（2026-06-20 完成）：

**搜索页**（Strategy A）：DOM 使用 `div.result-content` 容器，按链接 class 分类（`l-card-ti` → 标题、`l-source` → 来源行、`l-container` → 视频卡片）。

**首页 feed**（Strategy B）：文章在同一大容器内，用 TreeWalker 按 DOM 顺序配对 `<a class="title">` 与时间标记文本节点。

**用户主页**（Strategy C）：profile feed 的帖子不是独立链接，内容通过 innerText 行解析：时间行（`"作者名3天前"`）作为分隔符，每条时间行之前的内容聚合为一个帖子，链接通过 `linkMap` 子串匹配填充。

**优势**：
- 零 Chrome CDP 依赖（隐身模式），用户体验好
- 内置反爬（TLS 指纹、Cloudflare bypass、广告拦截）
- `real_chrome=True` 可继承用户 Chrome 登录态（用户页场景）
- 统一 `page_action` 模式，提取逻辑可复用

**劣势**：
- SPA 页面的 DOM 提取仍需逆向工程（和 Playwright 一样）
- 无法解决登录墙（和 CDP/Playwright 一样）
- 需额外安装：`pip install "scrapling[fetchers]"` + `scrapling install`

### 6.5 AI Agent 委托 (Claude Crawler)

```
后端 → 启动 Claude Code CLI 子进程
     → Claude 使用 web-access skill + CDP 浏览器抓取
     → 写 JSON 文件 → 后端读取
```

**定位**：理论覆盖最广但默认**禁用**

**流程**：
1. 构造 prompt（含目标 URL、输出 JSON 格式）
2. 写入临时 prompt 文件
3. `claude -p {prompt_content}` 子进程
4. 轮询等待结果 JSON（5 分钟，每 5s 检查）
5. 读取 JSON → `CrawlResult`

**优势**：
- 理论最智能：可自适应页面结构变化，无需写选择器
- 覆盖 7 个平台（最广）

**劣势**：
- 5 分钟超时
- 结果不稳定（AI 输出格式可能不一致）
- 依赖 Claude Code CLI
- 成本高（每次爬取消耗 token）

### 6.6 技术路线对比总览

| 维度 | OpenCLI | CDP | Scrapling | Playwright | Claude AI |
|------|---------|-----|-----------|------------|-----------|
| **覆盖平台** | 4 | 1 | 1（头条） | 7 | 7 |
| **速度** | 快（~10s） | 中（~30s） | 中（~15s） | 慢（~60s） | 极慢（~5min） |
| **可靠性** | 高 | 中 | 中高 | 高 | 低 |
| **评论提取** | ✗ | ✓ | ✗ | ✓ | ✓（不稳定） |
| **登录态** | Chrome 扩展 | Chrome CDP | headless / real_chrome | headless / CDP | Chrome CDP |
| **维护成本** | 低（社区） | 中（JS 脚本） | 低（adaptive CSS） | 中（DOM 选择器） | 高（Prompt 调优） |
| **运行依赖** | opencli npm 包 | CDP Proxy + Chrome | Scrapling + Chromium | Playwright + Chromium | Claude Code CLI + Chrome |
| **默认启用** | ✓ | ✓ | ✓ | ✓ | ✗ |

---

## 7. 三大业务场景

### 7.1 社交账号监测 (`monitor.py`)

```
APScheduler 定时触发
  │
  ▼
遍历活跃 Target:
  │
  ├─ 社交账号 (type="social"):
  │   CrawlerRouter.crawl(platform, account_name, url)
  │     → OpenCLI → CDP → Scrapling → Playwright 降级
  │
  └─ 网站 (type="website"):
      WebsiteCrawler.crawl(url, css_selector)
  │
  ▼
filter_posts(posts, post_limit, time_range_days)
  │
  ▼
AI 摘要 (summarizer.py)
  │ 支持多模态（图片 + 文本）
  │ 多提供商: MiniMax / DeepSeek / MiMo
  │
  ▼
存入 MonitorResult
  ├─ raw_content: JSON 序列化的帖子列表（含 published_at）
  ├─ summary: AI 摘要
  ├─ crawl_method: 实际使用的爬取方式
  └─ screenshot: 可选页面截图
```

**关键特性**：
- 异步执行：`POST /api/schedule/run/{id}` 立即返回 `pending + result_id`
- 爬取方法追踪：`MonitorResult.crawl_method` 记录实际使用的爬取方式
- 时间筛选：`time_range_days > 0` 时排除超出范围的帖子和无时间戳帖子
- 图文分析：多模态 LLM 分析帖子配图，融入摘要

### 7.2 舆情关键词搜索 (`sentiment.py`)

```
POST /api/sentiment/search (keyword, platforms)
  │
  ▼
创建 SentimentTask (status=pending)
  │
  ▼
后台 asyncio.create_task:
  │
  asyncio.gather(
    search_weibo(keyword),        # AutoCLI → Playwright 降级
    search_douyin(keyword),       # Playwright + CDP
    search_xiaohongshu(keyword),  # OpenCLI
    search_toutiao(keyword),      # Playwright + CDP
    search_108community(keyword), # Playwright headless
  )
  │
  ▼
每条帖子 → calculate_impact() → 影响力评分
  │
  ▼
task.status = "completed"
  │
  ▼
前端轮询 GET /api/sentiment/tasks/{id}
```

**影响力公式**（详见第 8 节）：
```
score = engagement_score × platform_weight × time_decay × 100
```

**关键特性**：
- 5 平台并发搜索（`asyncio.gather`）
- 自适应评分：百分位优先（≥1000 样本），冷启动降级为 log10 归一化
- 自适应分母：只对实际返回的指标加权平均（`metrics_partial` 标记）
- 30 天自动清理（scheduler 每日 4:07 AM）

### 7.3 热门话题抓取 (`autocli_service.py`)

```
POST /api/hot-topics/fetch (异步，立即返回 pending)
  │
  ▼
fetch_multiple(platforms):
  │
  ├─ browser 模式（串行）:
  │   weibo → zhihu → bilibili → twitter → douban_movie
  │   → douban_book → xueqiu
  │   每个: autocli → 失败 → Playwright 降级（仅微博）
  │
  ├─ public 模式（并发）:
  │   asyncio.gather(
  │     v2ex, hackernews, reddit, linux-do,
  │     bbc, google_trends, stackoverflow
  │   )
  │
  └─ github 特殊:
      httpx.get("github.com/trending") + BeautifulSoup
  │
  ▼
TopicItem 列表 → 存入 HotTopic 表
  │
  ▼
前端每 3s 轮询刷新
```

**16 平台模式分类**：

| 模式 | 平台 | 特点 |
|------|------|------|
| **browser** | weibo, zhihu, bilibili, twitter, douban_movie, douban_book, xueqiu | 需要 Chrome 登录态，串行执行 |
| **public** | v2ex, hackernews, reddit, linux-do, bbc, google_trends, stackoverflow | 无需登录，并发执行 |
| **custom** | github | httpx 直接抓取，不用 AutoCLI |

**关键特性**：
- 异步模式避免超时（前端轮询替代同步等待）
- 标准化输出：`TopicItem` 统一不同平台的原始 JSON 格式
- 微博热搜 Playwright 降级：AutoCLI 不可用时自动切换到 headless API 方案
- GitHub 独立实现：用 httpx + BeautifulSoup 替代 AutoCLI（更稳定）

---

## 8. 舆情影响力评分体系

位于 `services/scoring.py`。

### 8.1 评分公式

```
impact_score = engagement_score × platform_weight × time_decay × 100
```

### 8.2 互动评分 (`engagement_score`)

**指标权重**：

| 指标 | 权重 | 设计依据 |
|------|------|----------|
| views | 0.5 | 被动指标，参与深度最低 |
| likes | 1.0 | 基础互动 |
| bookmarks | 2.0 | 有意保存，高价值 |
| comments | 2.5 | 主动参与，产出内容 |
| shares | 3.5 | 最高价值传播行为 |

**归一化策略**（两级）：

| 条件 | 方法 | 说明 |
|------|------|------|
| 有 ≥1000 样本的 PlatformStats | 百分位插值法 | 在 p50-p99 之间线性插值 |
| 样本不足（冷启动） | log10 归一化 | `log10(v+1) / log10(max+1)` |

**自适应分母**：只对平台**实际返回**的指标加权求平均。
- `metrics_partial = True`：排除值为 0 的指标权重
- `metrics_partial = False`：所有 5 个指标参与计算

### 8.3 平台权重 (`platform_weight`)

```
raw_weight = log10(平台MAU) / log10(最大平台MAU)
platform_weight = clamp(raw_weight, 0.3, 0.7)
```

**默认 MAU 值**：

| 平台 | MAU | 权重 |
|------|-----|------|
| 抖音 | 7.3 亿 | 0.70 |
| 微博 | 5.86 亿 | 0.66 |
| 今日头条 | 3.5 亿 | 0.61 |
| 小红书 | 3 亿 | 0.59 |
| 108社区 | 50 万 | 0.30（钳位下限） |

### 8.4 时间衰减 (`time_decay`)

```
λ = ln(2) / half_life_days           # 默认半衰期 4 天
time_decay = e^(-λ × days_ago)
```

**无时间戳处理**：
- 帖子无 `published_at` → 默认按 **7 天前**计算（`time_decay ≈ 0.30`）
- 不给予最高新鲜度（早期版本的 bug）

### 8.5 percentile 统计维护

`PlatformStats` 表存储每个平台的每个指标的百分位阈值（p50 / p75 / p90 / p95 / p99）。

`refresh_platform_stats()` 从历史 `SentimentPost` 数据重新计算，随数据增长定期刷新。

---

## 9. 时间规范化方案

（2026-06-14 全量实施）

### 9.1 设计原则

- **统一存储**：所有 `published_at` 存为 **naive UTC datetime**（`tzinfo=None`），兼容 SQLite
- **统一解析入口**：`crawlers/base.py` 提供两个公共函数，禁止各爬虫自行实现
- **显式假设**：中文平台默认视为北京时间（`assume_utc=False`），英文平台视为 UTC（`assume_utc=True`）

### 9.2 解析函数

#### `parse_relative_time(text, now=None) → datetime | None`

解析中英文相对时间字符串。

**正则表达式**：
```python
_RELATIVE_EN = re.compile(r'(\d+)\s*(minute|hour|day|week|month|year)s?\s*ago', re.I)
_RELATIVE_ZH = re.compile(r'(\d+)\s*个?\s*(分钟|小时|天|周|月|年)前')
```

**单位映射**：分钟→minutes, 小时→hours, 天→days, 周→weeks, 月→months(×30天), 年→years(×365天)

**示例**：
- `"3 days ago"` → 3 天前的 naive UTC datetime
- `"2小时前"` → 2 小时前的 naive UTC datetime
- `"2个月前"` → 60 天前的 naive UTC datetime

#### `parse_absolute_time(text, assume_utc=False) → datetime | None`

解析绝对时间字符串。

**支持的格式**：`%Y-%m-%d %H:%M:%S`、`%Y-%m-%d %H:%M`、`%Y-%m-%d`、`%m-%d`（补当前年份）、`%Y/%m/%d %H:%M:%S`、`%Y/%m/%d %H:%M`、`%Y/%m/%d`

**时区处理**：
- `assume_utc=False`（默认）：naive datetime 视为北京时间，转换为 UTC
- `assume_utc=True`：直接视为 UTC

### 9.3 各平台时间提取实现

| 平台 | 时间来源 | 解析方式 | 实现位置 |
|------|----------|----------|----------|
| **微博** | API `created_at` 字段 | `"%a %b %d %H:%M:%S %z %Y"` + UTC 转换 | `weibo_crawler.py` (3 处) |
| **X/Twitter** | `<time datetime="...">` ISO 8601 | `fromisoformat()` + UTC 转换 | `x_crawler.py` |
| **YouTube** | `#metadata-line` 第 2 个 span | `parse_relative_time`（英文） | `youtube_crawler.py` |
| **抖音** | `span[class*="time"]` | `parse_relative_time` 或 `parse_absolute_time` | `douyin_crawler.py` |
| **今日头条** | `span[class*="time"]` | `parse_relative_time` 或 `parse_absolute_time` | `toutiao_crawler.py` |
| **108社区** | 论坛时间列 `td:last-child` | `parse_absolute_time` | `tiantai108_crawler.py` |
| **小红书** | 列表页无时间 | 暂跳过 | — |

### 9.4 消费端时间处理

**filter_posts**（`crawlers/base.py`）：
```python
if time_range_days > 0:
    cutoff = datetime.now(TZ_UTC).replace(tzinfo=None) - timedelta(days=time_range_days)
    filtered = [p for p in filtered
                if p.published_at is not None and p.published_at >= cutoff]
```
无时间戳帖子在时间筛选激活时被**排除**（而非放行）。

**scoring.py**：无时间戳帖子 `time_decay` 默认 7 天惩罚（≈0.30）。

**前端**（`SentimentPage.tsx`）：后端返回 naive UTC 字符串，前端追加 `'Z'` 强制按 UTC 解析，再格式化到北京时间显示。

### 9.5 新增爬虫强制要求

CLAUDE.md 红线规则：
> **新增爬虫必须设置 `published_at`**：使用 `parse_relative_time()` 或 `parse_absolute_time()` 解析，中文平台默认视为北京时间转 UTC。

---

## 10. 关键技术细节

### 10.1 Windows 兼容性

| 问题 | 影响 | 解决方案 |
|------|------|----------|
| Python 3.14 `SelectorEventLoop` 不支持 `create_subprocess_exec` | OpenCLI 调用 | 改用 `subprocess.run` + `asyncio.to_thread` |
| Playwright 协程与主事件循环冲突 | 所有 Playwright 爬虫 | `_run_crawler_in_thread()` 线程池 + `ProactorEventLoop` |
| PowerShell 语法差异 | Claude crawler | 使用 `-Command` + `Get-Content -Raw` 读取 prompt 文件 |

### 10.2 登录态管理

| 方式 | 适用爬虫 | 要求 |
|------|----------|------|
| Chrome 扩展连接 | OpenCLI / AutoCLI | Chrome 已登录目标平台 + 扩展已连接 |
| Chrome CDP (localhost:9222) | douyin / toutiao | Chrome 启动参数 `--remote-debugging-port=9222` |
| CDP Proxy (localhost:3456) | CDP crawler | web-access skill 运行中 |
| 无头浏览器 + Cookie 持久化 | weibo | 先访问 m.weibo.cn 建立 Cookie（`domcontentloaded` 策略） |
| 无头浏览器（无登录） | youtube / xiaohongshu / tiantai108 / website | 公开内容，无需登录 |

### 10.3 反爬与稳定性

| 平台 | 风险 | 缓解措施 |
|------|------|----------|
| 微博 | m.weibo.cn 长连接导致 `networkidle` 永不触发 | `domcontentloaded` + 3s sleep |
| 微博 | `mblog.pics` 类型不一致（list vs dict） | `isinstance(pics_raw, dict)` 兼容处理 |
| X/Twitter | 登录墙 | 检测 `"Log in"` + `"Sign up"` 文本，返回明确错误 |
| X/Twitter | DOM 频繁变化 | 降级链冗余（OpenCLI → CDP → Playwright） |
| 抖音 | SPA 动态渲染 | 多等待 + 多选择器 fallback |
| 108社区 | 搜索 URL 不明确 | 两阶段：直接 URL 尝试 → CDP 辅助搜索 |
| YouTube | 选择器脆弱 | `#video-title` / `#metadata-line` 相对稳定 |

### 10.4 AI 摘要集成

- **多提供商**：MiniMax / DeepSeek / MiMo（通过 `AI_PROVIDER` 环境变量切换）
- **多模态**：图片 URL 随文本传入 API，支持视觉分析，失败自动回退纯文本
- **限制**：每帖最多 5 张图片，每批次最多 10 张
- **System Prompt**：可通过 `SUMMARIZE_POSTS_PROMPT` / `SUMMARIZE_WEBSITE_PROMPT` 环境变量自定义

### 10.5 图片代理

微博图片直接引用返回 403（防盗链）。前端 `PostImages` 组件自动将 weibo 图片 URL 转为代理 URL：
```
/api/tools/proxy/image?url={encoded_weibo_image_url}
```
代理添加 `Referer: https://weibo.com` 头绕过 CDN 检查。

---

## 11. 当前痛点与改进方向

### 11.1 已识别痛点

| 痛点 | 影响范围 | 影响程度 | 当前状态 |
|------|----------|----------|----------|
| **抖音/头条需用户 Chrome CDP 登录态** | 账号监测 + 舆情搜索 | 高 | 框架就绪，交互不稳定。需要用户手动启动 Chrome with `--remote-debugging-port=9222` |
| **小红书列表页无互动数据和时间** | 账号监测 | 高 | 仅提取 title + url，舆情搜索依赖 OpenCLI |
| **X/Twitter 登录墙 + DOM 频繁变化** | 账号监测 + 舆情 | 中 | 已有三层降级（OpenCLI → CDP → Playwright），但无头像/分享数 |
| **微博无公开浏览量** | 舆情评分 | 中 | views 始终为 0，`metrics_partial` 自适应分母部分缓解 |
| **AutoCLI 依赖 Chrome 扩展连接** | 热门话题 | 中 | 仅微博有 Playwright 降级，其他 6 个 browser 平台无备选 |
| **108社区搜索 URL 模式猜测** | 舆情搜索 | 低 | 未充分测试，4 种 URL 模式均为尝试性 |
| **抖音搜索交互逆向未完成** | 舆情搜索 | 高 | JS 注入 fallback 策略可用但质量不稳定 |
| **Claude AI Agent 默认禁用** | 全场景 | 低 | 5 分钟超时 + 结果不稳定，不适合实时场景 |

### 11.2 改进方向

1. **完善 browser 平台 Playwright 降级**：为 zhihu / bilibili / twitter / douban 等补充 Playwright headless 备选方案
2. **小红书深度爬取**：进入详情页提取互动数据和时间（代价：每帖 +30s）
3. **抖音搜索逆向**：完成 SPA 交互逆向，获取更可靠的搜索结果
4. **统一登录态管理**：探索将 Cookie/Token 集中管理，减少对用户 Chrome 的依赖
5. **爬虫健康监控**：定期检测各平台 DOM 选择器是否仍有效，提前预警

---

## 12. 文件清单

### 爬虫层

| 文件 | 职责 | 代码行数（约） |
|------|------|---------------|
| `crawlers/base.py` | 数据结构定义 + PlaywrightCrawler 基类 + 时间解析工具 + filter_posts + 线程隔离 | ~190 |
| `crawlers/router.py` | CrawlerEntry + CrawlerRouter 降级路由 | ~65 |
| `crawlers/__init__.py` | 爬虫注册 + build_default_router 组装 | ~80 |
| `crawlers/weibo_crawler.py` | 微博：Playwright + m.weibo.cn 移动 API | ~360 |
| `crawlers/x_crawler.py` | X/Twitter：Playwright DOM 抓取 | ~125 |
| `crawlers/youtube_crawler.py` | YouTube：Playwright DOM 抓取 | ~99 |
| `crawlers/xiaohongshu_crawler.py` | 小红书：Playwright DOM 抓取 | ~80 |
| `crawlers/douyin_crawler.py` | 抖音：Playwright 连接用户 Chrome | ~220 |
| `crawlers/toutiao_crawler.py` | 今日头条：Playwright 连接用户 Chrome | ~147 |
| `crawlers/tiantai108_crawler.py` | 108社区：Playwright headless + CDP 辅助搜索 | ~194 |
| `crawlers/opencli_crawler.py` | OpenCLI CLI 子进程调用 | ~344 |
| `crawlers/cdp_crawler.py` | CDP Proxy API 直连浏览器 | ~298 |
| `crawlers/claude_crawler.py` | Claude Code CLI 委托爬取 | ~264 |
| `crawlers/website_crawler.py` | 通用网站：Playwright headless | ~31 |

### 业务服务层

| 文件 | 职责 | 关键函数 |
|------|------|----------|
| `services/monitor.py` | 社交账号监测编排 | 定时执行 → Router 爬取 → AI 摘要 → 存库 |
| `services/sentiment.py` | 舆情关键词搜索编排 | `run_sentiment_search()` — 并发搜索 + 评分 + 存储 |
| `services/scoring.py` | 影响力评分引擎 | `calculate_impact()` — 互动 × 平台权重 × 时间衰减 |
| `services/autocli_service.py` | 热门话题 AutoCLI 抓取 | `fetch_hot_topics()` / `fetch_multiple()` |
| `services/summarizer.py` | AI 摘要生成 | `_call_ai()` — 多提供商 + 多模态 |

### 文档

| 文件 | 用途 |
|------|------|
| `docs/data-fetching-architecture.md` | 架构全景图（精简版） |
| `docs/data-fetching-detailed.md` | 本文档 — 技术方案详解 |

---

*最后更新：2026-06-20*
*项目路径：`E:\Gary\hebo\claude_projects\intel-monitor`*
