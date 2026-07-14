# Intel Monitor — 监控体验优化设计

> 日期: 2026-04-30
> 状态: 已批准

## 背景

intel-monitor 项目在实际使用中暴露出以下问题：

1. 新增社交账号点击执行后，仪表盘短暂显示"监测失败"，但实际监测仍在运行并最终输出结果
2. 新增账号后 OpenCLI 未及时处理，导致首次监测大概率失败
3. 监测定时仅支持每天一次，不支持多次定时或灵活 cron 表达式
4. 无法控制抓取的贴文时间范围和数量
5. 应用登录失败时前端无错误提示
6. 爬取无降级机制，OpenCLI 失败即标记 failed

## 设计方案

采用逐点修复策略（方案 A），按优先级分 6 个独立改动，每个可单独验证。

---

### 1. 状态显示修复

**问题根因**：前端调用 `POST /api/schedule/run/{id}` 是同步阻塞的，但前端可能在 API 返回前触发了列表刷新，此时数据库中还是上一次的旧结果。

**改动**：

- **后端 `routers/schedule.py`**：执行 API 改为异步——收到请求后立即创建 MonitorResult（status="pending"）并 flush 到数据库，返回 `{status: "pending", result_id: xxx}`，然后后台异步执行爬取
- **前端 SocialAccountsPage.tsx**：点击"执行"时，乐观设置该行为"监测中..."状态；收到 response 后用 `result_id` 开始轮询（每 2 秒查一次 `/api/results/{result_id}`），直到状态变为 success/failed
- **前端 DashboardPage.tsx**：对 pending 状态的结果，自动轮询刷新直到状态变更

**涉及文件**：
- `backend/routers/schedule.py`
- `frontend/src/pages/SocialAccountsPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`

---

### 2. 爬取降级链路

**设计方案**：在 `monitor.py` 中新增 `crawl_with_fallback()` 统一入口。

**降级顺序**：OpenCLI → CDP → Playwright

```
crawl_with_fallback(platform, account_url, post_limit, time_range_days)
  ├─ 尝试 OpenCLI（仅 x/xiaohongshu/reddit/bilibili）
  │   └─ 失败 → 记录日志 + error_message，继续
  ├─ 尝试 CDP（需要 Chrome 调试端口可用）
  │   └─ 失败 → 记录日志 + error_message，继续
  └─ 尝试 Playwright（兜底）
      └─ 失败 → 标记 MonitorResult 为 failed
```

**关键细节**：
- 每级降级时在 MonitorResult 的 `error_message` 中记录失败原因
- 最终成功时记录使用的 crawler 方法到 `crawl_method` 新字段
- `post_limit` 和 `time_range_days` 参数传递给每个 crawler

**MonitorResult 模型新增字段**：
- `crawl_method: str` — 实际使用的 crawler（opencli/cdp/playwright）

**涉及文件**：
- `backend/services/monitor.py`
- `backend/models/result.py`
- `backend/crawlers/opencli_crawler.py`
- `backend/crawlers/cdp_crawler.py`
- `backend/crawlers/x_crawler.py`（及其他 Playwright crawler）

---

### 3. 新增账号预热 + 验证

**设计方案**：`POST /api/targets` 创建 target 后触发异步预热验证流程。

**流程**：
1. 创建 Target 记录，返回 HTTP 响应（不阻塞）
2. 异步任务启动：
   - OpenCLI 预热：调用 opencli 加载账号浏览器会话 → 更新 `target.opencli_ready`
   - 验证爬取：调用 `crawl_with_fallback()` 抓取一次 → 创建 MonitorResult
   - 更新 `target.last_verify_status` 和 `target.last_verify_method`

**Target 模型新增字段**：
- `opencli_ready: bool = False` — OpenCLI 会话是否就绪
- `last_verify_status: str = "pending"` — 最近验证结果（pending/success/failed）
- `last_verify_method: str` — 验证使用的 crawler 方法

**前端**：
- 创建 target 后，列表中该行显示"验证中..."标签
- 验证完成后自动刷新，显示验证结果

**涉及文件**：
- `backend/routers/targets.py`
- `backend/models/target.py`
- `backend/schemas/target.py`
- `frontend/src/pages/SocialAccountsPage.tsx`

---

### 4. 调度增强：多次定时 + Cron 表达式

**Target 模型变更**：
- 新增 `cron_schedule: str` — 存储一个或多个 cron 表达式，分号分隔（如 `"0 9 * * *;0 14 * * *;0 20 * * *"`）
- 保留 `monitor_hour` / `monitor_minute` 作为简单模式字段，与 `cron_schedule` 互斥

**前端 UI**：
- 添加/编辑 target 表单新增"调度模式"切换：
  - 简单模式（默认）：每天定时，选 hour + minute
  - 高级模式：输入 cron 表达式，支持添加多个，每个可独立删除
- 每个 cron 表达式旁显示"下次执行时间"预览

**后端 scheduler 变更**：
- `refresh_jobs()` 解析 `cron_schedule`，为每个表达式创建独立 cron job
- job ID 格式：`target_{id}_{index}`（如 `target_5_0`, `target_5_1`）
- 无效 cron 表达式跳过并记录日志，不影响其他有效表达式

**SettingsPage**：
- 调度状态列表中，同一 target 的多个 job 分组显示

**涉及文件**：
- `backend/models/target.py`
- `backend/schemas/target.py`
- `backend/services/scheduler.py`
- `backend/routers/schedule.py`
- `frontend/src/pages/SocialAccountsPage.tsx`
- `frontend/src/pages/SettingsPage.tsx`

---

### 5. 贴文参数：时间范围 + 数量上限

**Target 模型新增字段**：
- `post_limit: int = 10` — 抓取贴文数量上限
- `post_time_range_days: int = 0` — 只抓取最近 N 天贴文（0 = 不限制）

**前端 UI**：
- 添加/编辑 target 表单新增：
  - "抓取数量"：数字输入框，默认 10
  - "时间范围"：数字输入框 + "天"后缀，默认 0 表示不限

**各 Crawler 适配**：
- OpenCLI：已支持 `--limit`，映射 `post_limit`；时间范围在结果解析后按日期过滤
- CDP / Playwright：爬取后在解析阶段过滤——按发布日期筛掉超出范围的，再截取前 `post_limit` 条
- 过滤逻辑统一放在 `crawlers/base.py` 的工具函数中

**涉及文件**：
- `backend/models/target.py`
- `backend/schemas/target.py`
- `backend/crawlers/base.py`
- `backend/crawlers/opencli_crawler.py`
- `backend/crawlers/cdp_crawler.py`
- `backend/services/monitor.py`
- `frontend/src/pages/SocialAccountsPage.tsx`

---

### 6. 登录错误提示

**前端 LoginPage.tsx**：
- `handleLogin` 中 try-catch 包裹 API 调用
- catch 中从 `error.response.data.detail` 提取错误信息，用 `message.error()` 展示：
  - 401 → "用户名或密码错误"
  - 422 → "请输入用户名和密码"
  - 网络错误 → "网络连接失败，请检查服务是否运行"
  - 其他 → 显示 detail 或 "登录失败，请稍后重试"

**后端无需改动**：已有的 401 返回格式正确。

**涉及文件**：
- `frontend/src/pages/LoginPage.tsx`

---

## 实施顺序

1. 状态显示修复（影响最小，立即改善体验）
2. 登录错误提示（改动最小，快速完成）
3. 爬取降级链路（核心架构改动，后续功能依赖它）
4. 贴文参数（依赖降级链路中的参数传递）
5. 新增账号预热验证（依赖降级链路）
6. 调度增强（独立模块，最后做）
