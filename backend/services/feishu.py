# intel-monitor/backend/services/feishu.py
"""飞书机器人服务层。

- 长连接（WebSocket）接收私聊消息与卡片按钮回调，无需公网回调 URL
- 指令路由：/绑定 /帮助 /列表 /结果 /监测 /暂停 /恢复
- 监测结果推送：定时监测完成 → 摘要卡片；失败 → 告警卡片
- 未配置 FEISHU_ENABLED 时全部安全降级（不启动、不推送）
"""
import asyncio
import json
import logging
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)


def _preload_lark_ws():
    """在主事件循环启动前导入 lark_oapi.ws。

    lark-oapi 的 ws.Client 在模块导入时捕获事件循环（client.py 模块级
    ``loop = asyncio.get_event_loop()``），并在 start() 中
    ``loop.run_until_complete(...)`` 阻塞运行。若此处在 FastAPI 主循环已
    运行后导入，模块级 loop 会绑定到正在运行的主循环，导致
    "This event loop is already running"。因此必须在模块导入阶段（无运行中
    的循环）提前导入，使该 loop 独立于主循环。
    """
    try:
        import lark_oapi.ws  # noqa: F401
    except Exception:
        pass


_preload_lark_ws()

# 绑定验证码（内存存储，15 分钟有效）
_bind_codes: dict[str, dict] = {}
_BIND_CODE_TTL = timedelta(minutes=15)

_ws_client = None          # lark_oapi.ws.Client
_ws_thread: threading.Thread | None = None
_http_client = None        # lark_oapi.Client（发消息用）
_main_loop: asyncio.AbstractEventLoop | None = None

_PLATFORM_NAMES = {
    "x": "X (Twitter)",
    "youtube": "YouTube",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "weibo": "微博",
    "toutiao": "今日头条",
    "108community": "108天台社区",
}


def is_configured() -> bool:
    from config import settings
    return bool(settings.FEISHU_ENABLED and settings.FEISHU_APP_ID and settings.FEISHU_APP_SECRET)


# ─────────────────────────── 生命周期 ───────────────────────────

def start_feishu_client():
    """启动飞书长连接客户端（后台线程）。未配置时跳过。"""
    global _ws_client, _ws_thread, _http_client, _main_loop
    if not is_configured():
        logger.info("[feishu] 未配置 FEISHU_ENABLED/APP_ID/APP_SECRET，飞书机器人未启动")
        return
    try:
        import lark_oapi as lark
        from lark_oapi.ws import Client as WSClient
        from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
        from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger

        from config import settings

        _main_loop = asyncio.get_event_loop()
        _http_client = lark.Client.builder() \
            .app_id(settings.FEISHU_APP_ID) \
            .app_secret(settings.FEISHU_APP_SECRET) \
            .log_level(lark.LogLevel.ERROR) \
            .build()

        def _on_message(data: P2ImMessageReceiveV1):
            _submit_coro(_handle_message_event(data))

        def _on_card_action(data: P2CardActionTrigger):
            _submit_coro(_handle_card_action_event(data))
            return None

        handler = EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(_on_message) \
            .register_p2_card_action_trigger(_on_card_action) \
            .build()

        _ws_client = WSClient(
            settings.FEISHU_APP_ID,
            settings.FEISHU_APP_SECRET,
            log_level=lark.LogLevel.ERROR,
            event_handler=handler,
        )
        def _run_ws():
            try:
                _ws_client.start()
            except Exception as e:
                logger.error(f"[feishu] 长连接异常退出: {e}")

        _ws_thread = threading.Thread(target=_run_ws, daemon=True, name="feishu-ws")
        _ws_thread.start()
        logger.info("[feishu] 飞书机器人长连接已启动")
    except Exception as e:
        logger.exception(f"[feishu] 飞书客户端启动失败: {e}")
        _ws_client = None


def stop_feishu_client():
    """Best-effort 停止：lark ws Client 无公开 stop API，置空引用即可让
    旧连接因密钥失效自然断开（daemon 线程会随重连失败退出）。"""
    global _ws_client, _ws_thread
    if _ws_client is not None:
        try:
            stop = getattr(_ws_client, "stop", None)
            if callable(stop):
                stop()
        except Exception as e:
            logger.warning(f"[feishu] 停止飞书客户端异常: {e}")
        _ws_client = None
        _ws_thread = None


def _submit_coro(coro):
    """把事件处理协程提交到主事件循环（SDK 回调线程 → asyncio）。"""
    if _main_loop is not None and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, _main_loop)
    else:
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(coro)
        except Exception as e:
            logger.warning(f"[feishu] 无法调度事件协程: {e}")


# ─────────────────────────── 发消息 ───────────────────────────

async def _send_text(open_id: str, text: str):
    await _send_message(open_id, "text", {"text": text})


async def _send_card(open_id: str, card: dict):
    await _send_message(open_id, "interactive", card)


async def _send_message(open_id: str, msg_type: str, content: dict):
    if _http_client is None:
        logger.warning("[feishu] 客户端未就绪，消息未发送")
        return
    try:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        def _do_send():
            body = CreateMessageRequestBody.builder() \
                .receive_id(open_id) \
                .msg_type(msg_type) \
                .content(json.dumps(content, ensure_ascii=False)) \
                .build()
            req = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(body) \
                .build()
            resp = _http_client.im.v1.message.create(req)
            if not resp.success():
                code = resp.code if hasattr(resp, "code") else "?"
                logger.error(f"[feishu] 发送消息失败 code={code} msg={getattr(resp, 'msg', '')}")
            return resp

        await asyncio.to_thread(_do_send)
    except Exception as e:
        logger.exception(f"[feishu] 发送消息异常: {e}")


def _card(template: str, title: str, markdown: str, actions: list[dict] | None = None) -> dict:
    """飞书消息卡片 1.0 格式（im/v1 interactive）。

    注意：不能用 schema 2.0 + 顶层 elements 的混合结构——2.0 的元素在
    body.elements，顶层 elements 是 1.0 的字段；混用会被飞书拒绝
    （ErrCode 200621: unknown property: elements）。
    """
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}, "template": template},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": markdown}}],
    }
    if actions:
        card["elements"].append({"tag": "action", "actions": actions})
    return card


def _button(text: str, value: dict, button_type: str = "default") -> dict:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": button_type,
        "value": {k: str(v) for k, v in value.items()},
    }


# ─────────────────────────── 绑定验证码 ───────────────────────────

_bind_attempts: dict[str, dict] = {}  # open_id -> {"count": int, "locked_until": datetime}
_BIND_MAX_ATTEMPTS = 5
_BIND_LOCK_TTL = timedelta(minutes=15)


def generate_bind_code(user_id: int) -> str:
    """生成一次性绑定验证码（15 分钟有效，64bit 熵）。"""
    code = secrets.token_hex(8).upper()  # 16 位 = 64 bit
    _bind_codes[code] = {"user_id": user_id, "expires": datetime.now(timezone.utc) + _BIND_CODE_TTL}
    return code


async def _bind_open_id(open_id: str, code: str):
    from database import async_session
    from models.user import User

    now = datetime.now(timezone.utc)

    code = code.strip().upper()
    entry = _bind_codes.pop(code, None)
    if entry is not None and now <= entry["expires"]:
        # 有效码始终可用（限流只针对无效尝试）；绑定成功清空失败计数
        _bind_attempts.pop(open_id, None)
    else:
        # 无效/过期码：按 open_id 计数，5 次失败锁定 15 分钟
        attempt = _bind_attempts.get(open_id)
        if attempt is not None and attempt.get("locked_until") and now < attempt["locked_until"]:
            await _send_text(open_id, "⏳ 绑定尝试过于频繁，请 15 分钟后再试。")
            return
        count = (attempt.get("count", 0) if attempt else 0) + 1
        if count >= _BIND_MAX_ATTEMPTS:
            _bind_attempts[open_id] = {"count": 0, "locked_until": now + _BIND_LOCK_TTL}
            await _send_text(open_id, "❌ 绑定失败次数过多，已锁定 15 分钟。")
        else:
            _bind_attempts[open_id] = {"count": count, "locked_until": None}
            await _send_text(open_id, "❌ 绑定码无效或已过期，请在 Web 端重新生成。")
        return
    async with async_session() as db:
        user = await db.get(User, entry["user_id"])
        if user is None:
            await _send_text(open_id, "❌ 绑定失败：系统用户不存在。")
            return
        user.feishu_open_id = open_id
        user.feishu_push_enabled = True
        await db.commit()
        await _send_text(
            open_id,
            f"✅ 绑定成功！账号「{user.username}」已关联当前飞书会话。\n"
            f"输入 /帮助 查看可用指令。",
        )


# ─────────────────────────── 消息/卡片事件处理 ───────────────────────────

async def _handle_message_event(data):
    try:
        event = data.event
        sender = event.sender
        if sender.sender_type == "bot":
            return  # 忽略机器人自己
        open_id = sender.sender_id.open_id
        message = event.message
        if message.message_type != "text":
            return
        text = json.loads(message.content).get("text", "").strip()
        if not text:
            return
        logger.info(f"[feishu] 收到消息 open_id={open_id[:8]}... text={text[:50]}")
        await _route_command(open_id, text)
    except Exception as e:
        logger.exception(f"[feishu] 消息处理异常: {e}")


async def _handle_card_action_event(data):
    try:
        event = data.event
        operator = event.operator
        open_id = operator.open_id
        value = dict(event.action.value or {})
        action = value.get("action", "")
        logger.info(f"[feishu] 卡片回调 open_id={open_id[:8]}... action={action}")
        if action == "result":
            await _cmd_result(open_id, value.get("target_id", ""), value.get("target_type", "social_media"))
        elif action == "run":
            await _cmd_run(open_id, value.get("target_id", ""), value.get("target_type", "social_media"))
        elif action == "pause":
            await _set_user_push(open_id, False)
        elif action == "resume":
            await _set_user_push(open_id, True)
        elif action == "retry":
            await _cmd_run(open_id, value.get("target_id", ""), value.get("target_type", "social_media"))
    except Exception as e:
        logger.exception(f"[feishu] 卡片回调处理异常: {e}")


_CMD_PATTERN = re.compile(r"^/(绑定|结果|监测|帮助|列表|暂停|恢复|list|help)\s*(.*)$", re.IGNORECASE)
_CMD_MAP = {
    "绑定": "bind", "结果": "result", "监测": "run", "帮助": "help",
    "列表": "list", "暂停": "pause", "恢复": "resume",
}


async def _route_command(open_id: str, text: str):
    """文本指令路由。支持 /命令（带/不带空格均可）或自然语言前缀。"""
    text = text.strip()
    m = _CMD_PATTERN.match(text)
    if m:
        raw_cmd, arg = m.group(1), m.group(2).strip()
        cmd = _CMD_MAP.get(raw_cmd, raw_cmd.lower())
    else:
        # 自然语言前缀：帮助 / 列表 / 暂停 / 恢复 / 结果X / 监测X / 绑定X
        lowered = text.lower()
        if lowered == "帮助" or lowered == "help":
            cmd, arg = "help", ""
        elif lowered == "列表" or lowered == "list":
            cmd, arg = "list", ""
        elif lowered == "暂停":
            cmd, arg = "pause", ""
        elif lowered == "恢复":
            cmd, arg = "resume", ""
        elif lowered.startswith("结果"):
            cmd, arg = "result", text[2:].strip()
        elif lowered.startswith("监测"):
            cmd, arg = "run", text[2:].strip()
        elif lowered.startswith("绑定"):
            cmd, arg = "bind", text[2:].strip()
        else:
            cmd, arg = "", ""

    if cmd == "help":
        await _cmd_help(open_id)
    elif cmd == "bind":
        await _cmd_bind(open_id, arg)
    elif cmd == "list":
        await _cmd_list(open_id)
    elif cmd == "result":
        await _cmd_result(open_id, arg)
    elif cmd == "run":
        await _cmd_run(open_id, arg)
    elif cmd == "pause":
        await _set_user_push(open_id, False)
    elif cmd == "resume":
        await _set_user_push(open_id, True)
    else:
        await _send_text(open_id, "❓ 无法识别的指令，输入 /帮助 查看可用指令。")


async def _cmd_help(open_id: str):
    text = (
        "🤖 Intel Monitor 飞书助手\n\n"
        "/帮助 — 显示本帮助\n"
        "/绑定 <验证码> — 绑定 Web 端生成的验证码\n"
        "/列表 — 查看所有监测目标与最新状态\n"
        "/结果 <名称> — 查看目标最新监测摘要\n"
        "/监测 <名称> — 手动触发立即监测\n"
        "/暂停 — 暂停推送（全局）\n"
        "/恢复 — 恢复推送（全局）\n\n"
        "目标增删改请在 Web 端操作。"
    )
    await _send_text(open_id, text)


async def _cmd_bind(open_id: str, code: str):
    if not code:
        await _send_text(open_id, "用法：/绑定 <验证码>\n验证码在 Web 端「系统设置 → 飞书绑定」中生成。")
        return
    await _bind_open_id(open_id, code)


async def _get_user_by_open_id(open_id: str):
    from database import async_session
    from models.user import User
    async with async_session() as db:
        result = await db.execute(select(User).where(User.feishu_open_id == open_id))
        return result.scalar_one_or_none()


async def _cmd_list(open_id: str):
    from database import async_session
    from models.target import Target
    from models.website import WebsiteTarget
    from models.result import MonitorResult

    user = await _get_user_by_open_id(open_id)
    if user is None:
        await _send_text(open_id, "🔒 尚未绑定系统账号。请在 Web 端「系统设置 → 飞书绑定」生成验证码后发送 /绑定 <验证码>。")
        return

    async with async_session() as db:
        targets = (await db.execute(select(Target).where(Target.user_id == user.id).order_by(Target.created_at.desc()))).scalars().all()
        websites = (await db.execute(select(WebsiteTarget).where(WebsiteTarget.user_id == user.id).order_by(WebsiteTarget.created_at.desc()))).scalars().all()

        lines = []
        if not targets and not websites:
            lines.append("暂无监测目标。")
        for t in targets:
            status = "✅ 启用" if t.is_active else "⏸ 停用"
            push = "📢推" if t.push_enabled else "🔕"
            latest = await _latest_result(db, t.id, "social_media")
            latest_txt = "成功" if latest and latest.status == "success" else (latest.status if latest else "无记录")
            lines.append(f"📱 {_PLATFORM_NAMES.get(t.platform, t.platform)} @{t.account_name} {status}{push} | 最新:{latest_txt}")
        for w in websites:
            status = "✅ 启用" if w.is_active else "⏸ 停用"
            push = "📢推" if w.push_enabled else "🔕"
            latest = await _latest_result(db, w.id, "website")
            latest_txt = "成功" if latest and latest.status == "success" else (latest.status if latest else "无记录")
            lines.append(f"🌐 {w.name} {status}{push} | 最新:{latest_txt}")

        text = "📋 监测目标列表\n" + "\n".join(lines)
        text += "\n\n使用 /结果 <名称> 或 /监测 <名称> 操作。"
        await _send_text(open_id, text)


async def _latest_result(db, target_id: int, target_type: str):
    from models.result import MonitorResult
    result = await db.execute(
        select(MonitorResult)
        .where(MonitorResult.target_id == target_id, MonitorResult.target_type == target_type)
        .order_by(MonitorResult.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _resolve_target(user, query: str):
    """按 platform / 名称 / 序号解析目标。返回 (target_type, target_id, display_name) 或 None。"""
    from database import async_session
    from models.target import Target
    from models.website import WebsiteTarget

    query = query.strip()
    async with async_session() as db:
        targets = (await db.execute(select(Target).where(Target.user_id == user.id))).scalars().all()
        websites = (await db.execute(select(WebsiteTarget).where(WebsiteTarget.user_id == user.id))).scalars().all()

        # 序号：/列表 中显示的顺序（社交优先）
        if query.isdigit():
            idx = int(query)
            if 1 <= idx <= len(targets):
                t = targets[idx - 1]
                return "social_media", t.id, _PLATFORM_NAMES.get(t.platform, t.platform) + " @" + t.account_name
            if len(targets) < idx <= len(targets) + len(websites):
                w = websites[idx - len(targets) - 1]
                return "website", w.id, w.name

        # 平台名 / 账号名（社交）
        q_lower = query.lower()
        for t in targets:
            if t.platform == q_lower or q_lower in t.account_name.lower() or q_lower in _PLATFORM_NAMES.get(t.platform, "").lower():
                return "social_media", t.id, _PLATFORM_NAMES.get(t.platform, t.platform) + " @" + t.account_name
        # 网站名
        for w in websites:
            if q_lower in w.name.lower():
                return "website", w.id, w.name
    return None


async def _cmd_result(open_id: str, query: str, target_type_hint: str = ""):
    user = await _get_user_by_open_id(open_id)
    if user is None:
        await _send_text(open_id, "🔒 尚未绑定系统账号。请在 Web 端「系统设置 → 飞书绑定」生成验证码后发送 /绑定 <验证码>。")
        return
    if not query:
        await _send_text(open_id, "用法：/结果 <目标名称>，例如 /结果 微博。\n可用 /列表 查看全部目标。")
        return

    resolved = await _resolve_target(user, query)
    if resolved is None:
        await _send_text(open_id, f"❌ 未找到目标「{query}」。可用 /列表 查看全部目标。")
        return
    target_type, target_id, display = resolved

    from database import async_session
    async with async_session() as db:
        latest = await _latest_result(db, target_id, target_type)
        if latest is None:
            await _send_text(open_id, f"ℹ️ 目标「{display}」暂无监测结果。可用 /监测 {query} 立即监测。")
            return
        if latest.status == "success":
            summary = (latest.summary or "（无摘要）")[:800]
            card = _card(
                "blue",
                f"📊 监测结果 · {display}",
                f"**日期**：{latest.monitor_date}\n\n{summary}",
                actions=[
                    _button("立即监测", {"action": "run", "target_id": target_id, "target_type": target_type}),
                    _button("暂停推送", {"action": "pause"}),
                ],
            )
            await _send_card(open_id, card)
        elif latest.status == "failed":
            err = (latest.error_message or "未知错误")[:400]
            card = _card(
                "red",
                f"⚠️ 监测失败 · {display}",
                f"**日期**：{latest.monitor_date}\n\n{err}",
                actions=[
                    _button("重试", {"action": "retry", "target_id": target_id, "target_type": target_type}),
                    _button("暂停推送", {"action": "pause"}),
                ],
            )
            await _send_card(open_id, card)
        else:
            await _send_text(open_id, f"⏳ 目标「{display}」正在监测中，请稍后再试。")


async def _cmd_run(open_id: str, query: str, target_type_hint: str = ""):
    user = await _get_user_by_open_id(open_id)
    if user is None:
        await _send_text(open_id, "🔒 尚未绑定系统账号。请在 Web 端「系统设置 → 飞书绑定」生成验证码后发送 /绑定 <验证码>。")
        return
    if not query:
        await _send_text(open_id, "用法：/监测 <目标名称>，例如 /监测 微博。")
        return

    resolved = await _resolve_target(user, query)
    if resolved is None:
        await _send_text(open_id, f"❌ 未找到目标「{query}」。可用 /列表 查看全部目标。")
        return
    target_type, target_id, display = resolved

    from services.monitor import execute_monitor
    from database import async_session
    from models.result import MonitorResult

    # 创建 pending 记录后异步执行（与 Web 端 run_now 行为一致）
    async with async_session() as db:
        from datetime import date
        monitor_result = MonitorResult(
            target_id=target_id, target_type=target_type,
            monitor_date=date.today(), status="pending",
        )
        db.add(monitor_result)
        await db.commit()

    asyncio.create_task(execute_monitor(target_id, target_type))
    await _send_text(open_id, f"🚀 已开始监测「{display}」，完成后会自动推送结果。")


async def _set_user_push(open_id: str, enabled: bool):
    user = await _get_user_by_open_id(open_id)
    if user is None:
        await _send_text(open_id, "🔒 尚未绑定系统账号。")
        return
    from database import async_session
    async with async_session() as db:
        user.feishu_push_enabled = enabled
        await db.commit()
    await _send_text(open_id, "🔕 已暂停推送（全局）。恢复请发送 /恢复。" if not enabled else "📢 已恢复推送。")


# ─────────────────────────── 监测结果推送 ───────────────────────────

async def push_monitor_result(target_type: str, target_id: int):
    """监测完成后推送结果到绑定飞书用户。所有失败静默降级，不影响监测主流程。"""
    if _http_client is None:
        return
    try:
        from database import async_session
        from models.target import Target
        from models.website import WebsiteTarget
        from models.user import User

        async with async_session() as db:
            if target_type == "social_media":
                target = await db.get(Target, target_id)
                if target is None or not target.push_enabled:
                    return
                display = f"{_PLATFORM_NAMES.get(target.platform, target.platform)} @{target.account_name}"
                user = await db.get(User, target.user_id)
            else:
                target = await db.get(WebsiteTarget, target_id)
                if target is None or not target.push_enabled:
                    return
                display = target.name
                user = await db.get(User, target.user_id)

            if user is None or not user.feishu_open_id or not user.feishu_push_enabled:
                return

            latest = await _latest_result(db, target_id, target_type)
            if latest is None:
                return

            open_id = user.feishu_open_id
            if latest.status == "success":
                summary = (latest.summary or "（无摘要）")[:800]
                card = _card(
                    "green",
                    f"✅ 监测完成 · {display}",
                    f"**日期**：{latest.monitor_date}  **方法**：{latest.crawl_method or '-'}\n\n{summary}",
                    actions=[
                        _button("查看详情", {"action": "result", "target_id": target_id, "target_type": target_type}),
                        _button("立即监测", {"action": "run", "target_id": target_id, "target_type": target_type}),
                        _button("暂停推送", {"action": "pause"}),
                    ],
                )
                await _send_card(open_id, card)
            elif latest.status == "failed":
                err = (latest.error_message or "未知错误")[:400]
                card = _card(
                    "red",
                    f"⚠️ 监测失败 · {display}",
                    f"**日期**：{latest.monitor_date}\n\n{err}",
                    actions=[
                        _button("重试", {"action": "retry", "target_id": target_id, "target_type": target_type}),
                        _button("暂停推送", {"action": "pause"}),
                    ],
                )
                await _send_card(open_id, card)
    except Exception as e:
        logger.exception(f"[feishu] 推送监测结果失败: {e}")
