# X.com 舆情搜索 — 设计方案

> 状态: ✅ 已确认 | 日期: 2026-07-20

## 概述

在舆情搜索（Sentiment Monitoring）中新增对 X.com（Twitter）平台的关键词搜索功能。搜索方案采用 **OpenCLI (CDP) 为主，Playwright headless 为降级**，前端展示复用微博卡片布局并新增引用推文嵌套展示。

---

## 架构

```
POST /api/sentiment/search { keyword, platforms: ["x", ...], post_limit: 20 }
  │
  ├─ search_x_via_opencli(keyword, limit)
  │    │  opencli twitter search <keyword> --limit N -f json
  │    │  复用 Chrome CDP (localhost:9222) 登录态
  │    │
  │    ├─ 成功 → PostData[] (13 字段全)
  │    │         → 逐帖调 TweetDetail API 抓评论 (≤5 条/帖，1 页)
  │    │         → 评分 → 存储 → 返回
  │    │
  │    └─ 失败 → 降级 Playwright headless
  │
  ├─ [降级] Playwright headless + 持久化 profile
  │    │  调用 X GraphQL SearchTimeline API → 解析推文
  │    │  → 逐帖调 TweetDetail API 抓评论
  │    └─ 评分 → 存储 → 返回
  │
  └─ [降级失败] error_log["x"] = 错误信息
```

## 改动清单

| # | 层 | 文件 | 改动 |
|---|------|------|------|
| 1 | OpenCLI | `%APPDATA%/npm/.../opencli/clis/twitter/search.js` | `tweetToRow()` 补 `retweets`/`replies`/`bookmarks`/`name`/`avatar`；`columns` 声明加 5 列 |
| 2 | 后端·解析 | `backend/crawlers/opencli_crawler.py` | `_parse_twitter_posts()` 全字段映射 |
| 3 | 后端·搜索 | `backend/services/sentiment.py` | 加 `"x"` 平台分支 + 调用 `search_x_via_opencli` + 降级链 |
| 4 | 后端·降级 | `backend/crawlers/x_search_playwright.py` (**新建**) | Playwright persistent context + GraphQL SearchTimeline + TweetDetail 评论 |
| 5 | 后端·配置 | `backend/routers/sentiment.py` / `schemas/sentiment.py` | PLATFORM_INFO 加 X 平台 |
| 6 | 前端·展示 | `frontend/src/pages/SentimentPage.tsx` | 引用推文 QuotedTweet 组件 + 链接预览卡片 |

---

## 1. OpenCLI 适配器修补

### 现状

`search.js` 的 `tweetToRow()` 函数 (第 210-229 行) 只提取了部分字段。对比 `tweets.js`（用户推文命令）的 `extractTweet()`：

| 字段 | `tweets.js` | `search.js` (当前) |
|------|------------|-------------------|
| `id` | ✅ `rest_id` | ✅ |
| `author` | ✅ `screen_name` | ✅ |
| `bio` | ❌ | ✅ `description` |
| `text` | ✅ `full_text` / `note_tweet` | ✅ |
| `created_at` | ✅ | ✅ |
| `likes` | ✅ `favorite_count` | ✅ |
| `views` | ✅ `views.count` | ✅ |
| `url` | ✅ | ✅ |
| `has_media` | ✅ | ✅ |
| `media_urls` | ✅ | ✅ |
| `media_posters` | ✅ | ✅ |
| `card` | ❌ | ✅ `extractCard` |
| `quoted_tweet` | ✅ | ✅ |
| `retweets` | ✅ `retweet_count` | ❌ |
| `replies` | ✅ `reply_count` | ❌ |
| `bookmarks` | ❌ | ❌ |
| `name` (昵称) | ✅ | ❌ |
| `avatar` | ❌ | ❌ |

### 改动

`tweetToRow()` 函数改造为：

```js
function tweetToRow(result, seen) {
    const tweet = unwrapTweetResult(result);
    if (!tweet?.rest_id || seen.has(tweet.rest_id)) return null;
    seen.add(tweet.rest_id);
    const tweetUser = tweet.core?.user_results?.result;
    const bio = tweetUser?.legacy?.description || '';
    const legacy = tweet.legacy || {};
    return {
        id: tweet.rest_id,
        author: tweetUser?.core?.screen_name || tweetUser?.legacy?.screen_name || '',
        name: tweetUser?.legacy?.name || tweetUser?.core?.name || '',
        bio,
        avatar: tweetUser?.legacy?.profile_image_url_https || '',
        text: tweet.note_tweet?.note_tweet_results?.result?.text || legacy.full_text || '',
        created_at: legacy.created_at || '',
        likes: legacy.favorite_count || 0,
        retweets: legacy.retweet_count || 0,
        replies: legacy.reply_count || 0,
        bookmarks: legacy.bookmark_count || 0,
        views: tweet.views?.count || '0',
        url: `https://x.com/i/status/${tweet.rest_id}`,
        ...extractMedia(legacy),
        card: extractCard(tweet),
        quoted_tweet: extractQuotedTweet(tweet),
    };
}
```

`columns` 声明更新为：

```js
columns: [
    'id', 'author', 'name', 'bio', 'avatar', 'text', 'created_at',
    'likes', 'retweets', 'replies', 'bookmarks', 'views', 'url',
    'has_media', 'media_urls', 'media_posters', 'card', 'quoted_tweet'
]
```

---

## 2. 后端解析器 `_parse_twitter_posts()` 字段补全

### 文件: `backend/crawlers/opencli_crawler.py`

当前映射 vs 目标映射：

| PostData 字段 | 当前取值 | 目标取值 | 来源 |
|--------------|---------|---------|------|
| `content` | `text` \|\| `full_text` | 保持不变 | ✅ |
| `likes` | `likes` | 保持不变 | ✅ |
| `views` | `views` | 保持不变 | ✅ |
| `shares` | `retweets` | 保持不变 | ✅ |
| `comments_count` | `replies` | 保持不变 | ✅ |
| `bookmarks` | ❌ 未映射 | `bookmarks` | `legacy.bookmark_count` |
| `published_at` | ❌ 未映射 | 解析 `created_at` | `"Wed Jul 15 18:57:47 +0000 2026"` → naive UTC |
| `author_name` | ❌ 未映射 | `name` | 昵称，如 "Elon Musk" |
| `author_avatar` | ❌ 未映射 | `avatar` | `profile_image_url_https` |
| `author_followers` | ❌ 未映射 | 暂时置 0 | 搜索 API 未返回此字段 |
| `images` | `media_urls` | 保持不变 | ✅ |
| `url` | `x.com/{author}/status/{id}` | 保持不变 | ✅ |
| `quoted_tweet` | ❌ 未处理 | 序列化为 JSON 存 `quoted_tweet_json` | 前端嵌套展示用 |
| `card` | ❌ 未处理 | 序列化为 JSON 存 `card_json` | 链接预览卡片用 |

**`created_at` 时间解析**：X API 格式 `"Wed Jul 15 18:57:47 +0000 2026"`，使用 `datetime.strptime` 解析后转为 naive UTC（和项目内 `published_at` 统一标准一致）。

---

## 3. 舆情搜索集成

### 文件: `backend/services/sentiment.py`

在 `run_sentiment_search()` 的平台分发循环中添加：

```python
elif platform == "x":
    try:
        result = await search_x_via_opencli(keyword, limit=post_limit)
        if not result.success:
            raise Exception(result.error_message or "OpenCLI search failed")
    except Exception as e:
        logger.warning(f"X OpenCLI search failed, falling back to Playwright: {e}")
        try:
            result = await search_x_via_playwright(keyword, limit=post_limit)
        except Exception as e2:
            error_log["x"] = f"OpenCLI: {e}, Playwright: {e2}"
            posts_by_platform["x"] = []
            return
    posts_by_platform["x"] = result.posts
    # 逐帖抓评论
    await _fetch_x_comments(result.posts, limit=5)
```

### 降级链

```
search_x_via_opencli (CDP, 复用 Chrome)
    │
    ├─ 成功 → 返回 PostData[]
    │
    └─ 失败 → search_x_via_playwright (headless + 持久化 profile)
                │
                ├─ 成功 → 返回 PostData[]
                │
                └─ 失败 → error_log["x"] = 错误信息
```

### PLATFORM_INFO 配置

```python
"x": {
    "display_name": "X (Twitter)",
    "color": "#000000",
    "mau": 500_000_000,       # 5 亿月活
    "icon": "XOutlined",
    "base_url": "https://x.com",
    "supports_search": True,
}
```

---

## 4. Playwright 降级爬虫

### 文件: `backend/crawlers/x_search_playwright.py` (**新建**)

#### 核心逻辑

```python
async def search_x_via_playwright(keyword: str, limit: int = 20) -> CrawlResult:
    """
    Playwright headless 降级：使用持久化 profile 复用登录态，
    直接调用 X GraphQL SearchTimeline API。
    """
    user_data_dir = Path("backend/data/x_profile")
    user_data_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=True,
            # ...
        )
        page = await context.new_page()

        # 1. 获取 ct0 cookie
        cookies = await context.cookies("https://x.com")
        ct0 = next((c["value"] for c in cookies if c["name"] == "ct0"), None)
        if not ct0:
            return CrawlResult(success=False, error_message="X 未登录，请先在非 headless 模式登录")

        # 2. 调用 SearchTimeline GraphQL API
        tweets = await _fetch_search_timeline(page, ct0, keyword, limit)

        # 3. 转换为 PostData
        posts = [_parse_tweet_to_postdata(t) for t in tweets]

        return CrawlResult(success=True, posts=posts)
```

#### SearchTimeline GraphQL 调用

与 `search.js` 相同的 API 路径和参数：

- **Query ID**: 动态解析 (fallback: `Yw6L66Pw54NHKuq4Dp7b4Q`)
- **端点**: `/i/api/graphql/{queryId}/SearchTimeline`
- **Auth**: `Bearer {TWITTER_BEARER_TOKEN}` + `X-Csrf-Token: {ct0}`
- **分页**: `cursor` 参数逐页拉取直到 `limit`

---

## 5. 评论抓取

### 实现方式

逐帖调用 X `TweetDetail` GraphQL API，从返回的 conversation 中提取**前 5 条热门回复**。

- **API**: `TweetDetail` (queryId: `nBS-WpgA6ZG0CyNHD517JQ`)
- **请求数**: 每帖 1 次（不翻页），`limit` 帖共 N 次
- **预期耗时**: 20 帖约 20-30 秒（含 API 间 sleep）
- **提取逻辑**: 从 `threaded_conversation_with_injections_v2` instructions 中取 top-level 回复（排除主帖自身），按 `favorite_count` 排序取前 5

### OpenCLI 路径也做评论抓取

OpenCLI 的 `search` 命令不返回评论数据，因此 OpenCLI 成功后同样需要走一遍 Playwright 或 `httpx` 调 TweetDetail API。推荐直接 `httpx` 发 HTTP 请求（不需要浏览器），因为：
- X GraphQL API 可以直接用 `requests`/`httpx` 调用
- 不需要 DOM 解析
- 更快

```python
async def _fetch_x_comments_for_post(post_id: str, limit: int = 5) -> list[CommentData]:
    """用 httpx 直接调 TweetDetail API 抓评论"""
    # 从用户 Chrome 读取 ct0 cookie
    # GET /i/api/graphql/{queryId}/TweetDetail?variables=...
    # 从 threaded_conversation_with_injections_v2 提取 top-level 回复
    ...
```

---

## 6. 前端展示

### 文件: `frontend/src/pages/SentimentPage.tsx`

#### 图片处理
X 图片 URL (`pbs.twimg.com`) 复用现有 `/api/tools/proxy/image` 代理——`PostImages` 组件已统一走代理，无需改动。

#### 新增组件

**QuotedTweet** — 引用推文嵌套卡片：
- 缩进 12px + 左边框 2px (`#1DA1F2` 蓝或 `#333` 灰)
- 显示：引用作者 @ + 正文（截断 150 字符可展开）+ 缩略图
- 不递归展开（引用推文内部不再展开）
- `quoted_tweet_json` 字段如果非空则渲染

**LinkCard** — 链接预览卡片（card 字段）：
- 小卡片样式，显示域名 + 标题 + 缩略图
- 点击跳转原链接
- `card_json` 字段如果非空则渲染

#### 指标行
复用 `MetricRow` 组件，显示：点赞、评论、转发、收藏、浏览量（与小蓝鸟一致，数值格式化 ≥10000 显示万）。

---

## 7. 数据模型变更

### SentimentPost 模型

当前 `sentiment_posts` 表无需新增列。`quoted_tweet_json` 和 `card_json` 暂存于 `images_json` 旁或通过已有 TEXT 字段复用。

> **可选迁移**（后续迭代）：如果引用推文和卡片数据量大，可新增 `quoted_tweet_json TEXT` 和 `card_json TEXT` 列。

---

## 8. 评分影响

修复字段映射后，X 帖子将参与完整评分：

| 指标 | 权重 | 数据源 |
|------|------|--------|
| `views` | 0.5 | `tweet.views.count` |
| `likes` | 1.0 | `legacy.favorite_count` |
| `comments` | 2.5 | `legacy.reply_count` |
| `shares` | 3.5 | `legacy.retweet_count` |
| `bookmarks` | 2.0 | `legacy.bookmark_count` |
| `platform_weight` | 0.3~0.7 | MAU 5 亿 → `log10(500M)/log10(2.5B)` ≈ 0.943，钳位后 0.7 |
| `time_decay` | 0~1 | `created_at` → `published_at` |

修复前（缺 3 个字段）：X 帖子 `engagement_score` 被严重低估（缺少 shares=3.5 + bookmarks=2.0 共 5.5/9.5 权重）。

---

## 9. 首次登录引导

Playwright 持久化 profile (`backend/data/x_profile/`) 需要首次手动登录：

1. 启动非 headless 浏览器，导航至 `x.com/login`
2. 用户扫码或输入密码登录
3. 关闭浏览器，cookie/session 已持久化
4. 后续 headless 模式自动复用

> 可在系统设置页加 "X 登录状态检查" 功能（后续迭代）。

---

## 10. 已知限制

| 限制 | 说明 |
|------|------|
| X API 无公开 `followers_count` 字段 | SearchTimeline 返回的 user 对象不含 followers，`author_followers` 暂置 0 |
| 评论不翻页 | 每帖只取第一页 TweetDetail 的 top-level 回复 |
| OpenCLI 需要 Chrome CDP | `localhost:9222` 必须有 Chrome 运行，否则走 Playwright 降级 |
| 持久化 profile 首次需登录 | Playwright 降级前需手动在非 headless 模式登录一次 |

---

## 11. 实现顺序

| 步骤 | 模块 | 内容 |
|------|------|------|
| 1 | OpenCLI | 修补 `search.js` — 补字段 + columns |
| 2 | 后端·解析 | 修补 `_parse_twitter_posts()` — 全字段映射 |
| 3 | 后端·降级 | 新建 `x_search_playwright.py` — GraphQL + 评论 |
| 4 | 后端·搜索 | `sentiment.py` 加 `"x"` 分支 + 配置 |
| 5 | 前端·展示 | `SentimentPage.tsx` 加 QuotedTweet + LinkCard |
| 6 | 测试 | 端到端测试搜索 + 降级 + 评论 |
