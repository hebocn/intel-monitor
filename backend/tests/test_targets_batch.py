# intel-monitor/backend/tests/test_targets_batch.py
"""POST /api/targets/batch-update 批量修改测试。"""
import time

from fastapi.testclient import TestClient
import main


def _cleanup(client, username):
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("DELETE FROM monitor_results WHERE target_id NOT IN (SELECT id FROM targets) AND target_id NOT IN (SELECT id FROM website_targets)")
    con.execute("DELETE FROM targets WHERE user_id NOT IN (SELECT id FROM users WHERE username != ?)", (username,))
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()


def test_batch_update_targets(monkeypatch):
    # 禁用创建 target 后的预加热/验证爬取（避免真实 OpenCLI 探测导致测试超时）
    import routers.targets as rt
    monkeypatch.setattr(rt, "_warm_and_verify", lambda target_id: None)
    client = TestClient(main.app)
    uname = f"batch_tgt_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    ids = []
    try:
        for name in ["账号A", "账号B"]:
            r = client.post("/api/targets", headers=headers, json={
                "platform": "weibo", "account_name": name, "account_url": f"https://weibo.com/u/{int(time.time())}",
            })
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])

        # 批量关闭监测 + 飞书推送
        r = client.post("/api/targets/batch-update", headers=headers,
                        json={"target_ids": ids, "is_active": False, "push_enabled": False})
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 2
        assert set(r.json()["fields"]) == {"is_active", "push_enabled"}

        lst = client.get("/api/targets", headers=headers).json()
        for t in lst:
            assert t["is_active"] is False
            assert t["push_enabled"] is False

        # 只改推送，is_active 保持不变
        r = client.post("/api/targets/batch-update", headers=headers,
                        json={"target_ids": ids, "push_enabled": True})
        assert r.json()["updated"] == 2
        lst = client.get("/api/targets", headers=headers).json()
        for t in lst:
            assert t["push_enabled"] is True
            assert t["is_active"] is False

        # 空字段 → 400
        r = client.post("/api/targets/batch-update", headers=headers, json={"target_ids": ids})
        assert r.status_code == 400, r.text

        # 不存在的 id → 404
        r = client.post("/api/targets/batch-update", headers=headers,
                        json={"target_ids": [999999], "is_active": True})
        assert r.status_code == 404, r.text
    finally:
        _cleanup(client, uname)
