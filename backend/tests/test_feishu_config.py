# intel-monitor/backend/tests/test_feishu_config.py
"""PUT /api/feishu/config 与 GET /api/feishu/status 的端到端测试 + 安全用例。

注意：测试会临时改写 backend/.env 的 FEISHU_APP_SECRET（随后恢复原值），
并通过 monkeypatch 关闭 _schedule_reload，避免真实触发后端重启。
"""
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import main

import routers.feishu as rf


def _cleanup_user(client: TestClient, username: str):
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()


@pytest.fixture
def authed_client(monkeypatch):
    """注册新用户并返回 (client, headers)；关闭 reload 副作用。"""
    monkeypatch.setattr(rf, "_schedule_reload", lambda delay=1.2: None)
    client = TestClient(main.app)
    uname = f"feishu_cfg_test_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield client, headers
    _cleanup_user(client, uname)


def test_require_admin():
    from models.user import User
    ok = User(id=1, username="admin", password_hash="x")
    rf._require_admin(ok)  # 不应抛
    with pytest.raises(HTTPException) as ei:
        rf._require_admin(User(id=2, username="other", password_hash="x"))
    assert ei.value.status_code == 403


def test_config_forbidden_for_non_admin(authed_client, monkeypatch):
    client, headers = authed_client
    monkeypatch.setattr(rf, "_schedule_reload", lambda delay=1.2: None)
    r = client.put("/api/feishu/config", headers=headers, json={"app_secret": "A" * 32})
    assert r.status_code == 403, r.text


def test_config_injection_rejected(authed_client, monkeypatch):
    client, headers = authed_client
    monkeypatch.setattr(rf, "_schedule_reload", lambda delay=1.2: None)
    # 换行注入尝试：必须被 pydantic validator 拒绝（422）
    payload = "aaaaaaaa\nJWT_SECRET=forged"
    r = client.put("/api/feishu/config", headers=headers, json={"app_secret": payload})
    assert r.status_code == 422, r.text


def test_bind_code_attempt_limit(monkeypatch):
    """无效绑定码 5 次后锁定 15 分钟；有效码绑定成功后清空计数。"""
    import asyncio
    from services import feishu

    sent: list[str] = []

    async def _fake_send(open_id: str, text: str):
        sent.append(text)

    monkeypatch.setattr(feishu, "_send_text", _fake_send)
    monkeypatch.setattr(feishu, "_bind_codes", {})
    monkeypatch.setattr(feishu, "_bind_attempts", {})
    from models.user import User
    from database import async_session

    async def _run():
        # 备份 admin 原 open_id，测试后恢复（避免污染真实绑定）
        async with async_session() as db:
            admin = await db.get(User, 1)
            orig_open_id = admin.feishu_open_id if admin else None
        try:
            # 5 次无效尝试 → 锁定
            for _ in range(5):
                await feishu._bind_open_id("ou_test_attempt", "WRONG")
            assert "绑定失败次数过多" in sent[-1], sent

            # 有效码不受锁定影响，仍能成功绑定
            code = feishu.generate_bind_code(1)
            await feishu._bind_open_id("ou_test_attempt", code)
            assert sent[-1].startswith("✅"), sent[-1]
        finally:
            async with async_session() as db:
                admin = await db.get(User, 1)
                if admin is not None:
                    admin.feishu_open_id = orig_open_id
                    await db.commit()

    asyncio.run(_run())


def test_config_roundtrip(authed_client, monkeypatch):
    client, headers = authed_client
    monkeypatch.setattr(rf, "_schedule_reload", lambda delay=1.2: None)
    monkeypatch.setattr(rf, "_require_admin", lambda user: None)  # 绕过 admin 检查以测保存路径

    orig_env = rf._read_env()
    orig_secret = orig_env.get("FEISHU_APP_SECRET", "")
    assert orig_secret, "测试前提：.env 中需已配置 FEISHU_APP_SECRET"

    try:
        # 1) status：暴露 app_secret_set/app_id，不泄露明文 secret
        d = client.get("/api/feishu/status", headers=headers).json()
        assert d["app_secret_set"] is True
        assert d["app_id"].startswith("cli_")
        assert "FEISHU_APP_SECRET" not in str(d)

        # 2) 相同 secret → 无变化不重启
        r = client.put("/api/feishu/config", headers=headers, json={"app_secret": orig_secret})
        assert r.status_code == 200
        assert r.json()["restarted"] is False and r.json()["reloading"] is False, r.text

        # 3) 不同 secret → .env 更新 + reloading
        fake = "F" * 32
        r = client.put("/api/feishu/config", headers=headers, json={"app_secret": fake})
        assert r.status_code == 200
        assert r.json()["reloading"] is True, r.text
        assert rf._read_env()["FEISHU_APP_SECRET"] == fake

        # 4) 恢复原 secret
        r = client.put("/api/feishu/config", headers=headers, json={"app_secret": orig_secret})
        assert r.json()["reloading"] is True
        assert rf._read_env()["FEISHU_APP_SECRET"] == orig_secret
    finally:
        cur = rf._read_env()
        if cur.get("FEISHU_APP_SECRET") != orig_secret:
            cur["FEISHU_APP_SECRET"] = orig_secret
            rf._write_env(cur)
