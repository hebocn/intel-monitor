# intel-monitor/backend/tests/test_websites_batch.py
"""POST /api/websites/batch-update 批量修改测试。"""
import time

from fastapi.testclient import TestClient
import main


def _cleanup(client, username):
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("DELETE FROM website_targets WHERE user_id NOT IN (SELECT id FROM users WHERE username != ?)", (username,))
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()


def test_batch_update_websites():
    client = TestClient(main.app)
    uname = f"batch_site_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    ids = []
    try:
        for name in ["测试站A", "测试站B"]:
            r = client.post("/api/websites", headers=headers, json={"name": name, "url": f"https://{name}.com"})
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])

        # 批量关闭监测 + 飞书推送
        r = client.post("/api/websites/batch-update", headers=headers,
                        json={"website_ids": ids, "is_active": False, "push_enabled": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["updated"] == 2, body
        assert set(body["fields"]) == {"is_active", "push_enabled"}

        # 验证落库
        lst = client.get("/api/websites", headers=headers).json()
        for w in lst:
            assert w["is_active"] is False
            assert w["push_enabled"] is False

        # 只改推送（is_active 保持不变）
        r = client.post("/api/websites/batch-update", headers=headers,
                        json={"website_ids": ids, "push_enabled": True})
        assert r.status_code == 200 and r.json()["updated"] == 2
        lst = client.get("/api/websites", headers=headers).json()
        for w in lst:
            assert w["push_enabled"] is True
            assert w["is_active"] is False  # 未提供字段保持不变

        # 空字段 → 400
        r = client.post("/api/websites/batch-update", headers=headers, json={"website_ids": ids})
        assert r.status_code == 400, r.text

        # 他人的网站不可改（不存在 id）→ 404
        r = client.post("/api/websites/batch-update", headers=headers,
                        json={"website_ids": [999999], "is_active": True})
        assert r.status_code == 404, r.text
    finally:
        _cleanup(client, uname)
