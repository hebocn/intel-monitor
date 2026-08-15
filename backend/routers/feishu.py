# intel-monitor/backend/routers/feishu.py
import os
import re
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.user import User
from services.feishu import is_configured, generate_bind_code

router = APIRouter(prefix="/api/feishu", tags=["feishu"])

ENV_PATH = Path(__file__).parent.parent / ".env"

# 全局配置仅允许首个用户（initial_setup 创建的管理员）修改
ADMIN_USER_ID = 1

_SECRET_RE = re.compile(r"^[A-Za-z0-9._\-]{8,128}\Z")
_APP_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}\Z")

# reload 单飞：记录上次触发时间，最小间隔内不重复触发（防滥用 DoS）
_last_reload_ts: float = 0.0
_reload_lock = threading.Lock()
RELOAD_MIN_INTERVAL = 60.0


class FeishuConfigRequest(BaseModel):
    """保存飞书配置（App Secret 必填，App ID / 启用开关可选）。"""

    app_secret: str = Field(..., min_length=8, max_length=128)
    app_id: str | None = Field(None, max_length=64)
    enabled: bool | None = None

    @field_validator("app_secret")
    @classmethod
    def _check_secret(cls, v: str) -> str:
        # 防换行/控制字符注入 .env（pydantic str 默认允许换行）
        if not _SECRET_RE.match(v):
            raise ValueError("app_secret 只能包含字母、数字、点、下划线、连字符")
        return v

    @field_validator("app_id")
    @classmethod
    def _check_app_id(cls, v: str | None) -> str | None:
        if v is not None and not _APP_ID_RE.match(v):
            raise ValueError("app_id 只能包含字母、数字、下划线、连字符")
        return v


def _require_admin(user: User):
    if user.id != ADMIN_USER_ID:
        raise HTTPException(status_code=403, detail="仅系统管理员可修改飞书全局配置")


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _write_env(env: dict[str, str]):
    """原子写 .env（临时文件 + os.replace），避免并发写损坏。"""
    tmp = ENV_PATH.with_suffix(".env.tmp")
    tmp.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_PATH)


def _schedule_reload(delay: float = 1.2):
    """触发 uvicorn StatReload 重启 worker（touch main.py），使新配置生效。

    - 单飞：RELOAD_MIN_INTERVAL 内只允许一次，防循环调用造成重启 DoS
    - 不直接重建 lark ws 连接：lark-oapi 的 ws.Client 使用模块级单例事件循环，
      start() 以 run_until_complete(_select()) 永久阻塞，进程内无法安全热重启。
      复用项目 reload=True 机制自动重启。
    """
    global _last_reload_ts
    with _reload_lock:
        now = time.time()
        if now - _last_reload_ts < RELOAD_MIN_INTERVAL:
            return
        _last_reload_ts = now

    def _touch():
        time.sleep(delay)
        try:
            os.utime(Path(__file__).parent.parent / "main.py", None)
        except Exception:
            pass

    threading.Thread(target=_touch, daemon=True).start()


@router.get("/status")
async def feishu_status(user: User = Depends(get_current_user)):
    """飞书集成状态：是否配置、App 信息、当前用户绑定状态。"""
    from config import settings
    return {
        "configured": is_configured(),
        "app_id": settings.FEISHU_APP_ID,
        "app_secret_set": bool(settings.FEISHU_APP_SECRET),
        "bound": bool(user.feishu_open_id),
        "push_enabled": user.feishu_push_enabled,
    }


@router.put("/config")
async def save_feishu_config(
    req: FeishuConfigRequest,
    user: User = Depends(get_current_user),
):
    """保存飞书配置到 .env（仅管理员）；配置有变化时自动重启后端使新凭据生效。"""
    _require_admin(user)

    env = _read_env()
    new_env = dict(env)
    new_env["FEISHU_APP_SECRET"] = req.app_secret
    if req.app_id:
        new_env["FEISHU_APP_ID"] = req.app_id
    if req.enabled is not None:
        new_env["FEISHU_ENABLED"] = "true" if req.enabled else "false"
    else:
        new_env.setdefault("FEISHU_ENABLED", "true")

    changed = new_env != env
    reloading = False
    if changed:
        _write_env(new_env)
        # 重载 settings 单例（重新读取 .env）
        import config
        config.settings = config.Settings()
        _schedule_reload()
        reloading = True

    return {
        "ok": True,
        "configured": is_configured(),
        "restarted": changed,
        "reloading": reloading,
    }


@router.post("/bind-code")
async def create_bind_code(user: User = Depends(get_current_user)):
    """生成一次性绑定验证码（15 分钟有效，飞书里发 /绑定 <验证码>）。"""
    if not is_configured():
        raise HTTPException(status_code=400, detail="飞书机器人未配置，请在下方填写 App Secret 后保存")
    code = generate_bind_code(user.id)
    return {"code": code, "expires_minutes": 15, "hint": f"在飞书中向机器人发送：/绑定 {code}"}


@router.post("/unbind")
async def unbind_feishu(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑当前用户的飞书 open_id。"""
    user.feishu_open_id = None
    await db.commit()
    return {"bound": False}
