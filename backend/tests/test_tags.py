# intel-monitor/backend/tests/test_tags.py
"""标签功能测试：预置播种、CRUD、单账号打标签、批量打标签、删除级联。"""
import time

from fastapi.testclient import TestClient
import main


def _cleanup(username):
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("DELETE FROM target_tags WHERE target_id NOT IN (SELECT id FROM targets)")
    con.execute("DELETE FROM tags WHERE user_id IN (SELECT id FROM users WHERE username=?)", (username,))
    con.execute("DELETE FROM targets WHERE user_id IN (SELECT id FROM users WHERE username=?)", (username,))
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()


def _ensure_tables():
    """TestClient 不触发 lifespan/init_db，显式补建标签相关表（与 create_all 等价）。"""
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("""CREATE TABLE IF NOT EXISTS tags (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users (id),
        name VARCHAR(20) NOT NULL,
        color VARCHAR(20) NOT NULL,
        is_preset BOOLEAN,
        created_at DATETIME,
        CONSTRAINT uq_user_tag_name UNIQUE (user_id, name)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS target_tags (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        target_id INTEGER NOT NULL REFERENCES targets (id),
        tag_id INTEGER NOT NULL REFERENCES tags (id),
        created_at DATETIME,
        CONSTRAINT uq_target_tag UNIQUE (target_id, tag_id)
    )""")
    con.commit()
    con.close()


def test_tags_full_flow(monkeypatch):
    import routers.targets as rt
    monkeypatch.setattr(rt, "_warm_and_verify", lambda target_id: None)
    _ensure_tables()
    client = TestClient(main.app)
    uname = f"tag_user_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    try:
        # ── 预置标签：新用户应有「涉T账号」「涉Z账号」
        tags = client.get("/api/tags", headers=headers).json()
        names = {t["name"] for t in tags}
        assert names == {"涉T账号", "涉Z账号"}, names
        preset = next(t for t in tags if t["name"] == "涉T账号")
        assert preset["is_preset"] is True
        assert preset["target_count"] == 0

        # ── 新建自定义标签 + 重名校验 + 色板校验
        r = client.post("/api/tags", headers=headers, json={"name": "KOL", "color": "#06B6D4"})
        assert r.status_code == 201, r.text
        kol = r.json()
        assert kol["is_preset"] is False
        r = client.post("/api/tags", headers=headers, json={"name": "KOL", "color": "#06B6D4"})
        assert r.status_code == 409
        r = client.post("/api/tags", headers=headers, json={"name": "颜色越界", "color": "#FF0000"})
        assert r.status_code == 422

        # ── 建两个账号
        ids = []
        for name in ["账号甲", "账号乙"]:
            r = client.post("/api/targets", headers=headers, json={
                "platform": "weibo", "account_name": name,
                "account_url": f"https://weibo.com/u/{int(time.time() * 1000)}{name}",
            })
            assert r.status_code == 201, r.text
            assert r.json()["tags"] == []
            ids.append(r.json()["id"])

        # ── 单账号打标签（替换语义）
        r = client.put(f"/api/targets/{ids[0]}/tags", headers=headers,
                       json={"tag_ids": [preset["id"], kol["id"]]})
        assert r.status_code == 200, r.text
        got = {t["id"]: t for t in r.json()["tags"]}
        assert set(got) == {preset["id"], kol["id"]}
        assert got[kol["id"]]["name"] == "KOL"

        # 越权标签 id → 400
        r = client.put(f"/api/targets/{ids[0]}/tags", headers=headers, json={"tag_ids": [999999]})
        assert r.status_code == 400

        # 列表接口带出 tags
        lst = {t["id"]: t for t in client.get("/api/targets", headers=headers).json()}
        assert {t["id"] for t in lst[ids[0]]["tags"]} == {preset["id"], kol["id"]}
        assert lst[ids[1]]["tags"] == []

        # 更新账号不影响标签
        r = client.put(f"/api/targets/{ids[0]}", headers=headers, json={"account_name": "账号甲改"})
        assert r.status_code == 200
        assert len(r.json()["tags"]) == 2

        # ── 批量打标签
        r = client.post("/api/targets/batch-tags", headers=headers,
                        json={"target_ids": ids, "add_tag_ids": [kol["id"]]})
        assert r.status_code == 200 and r.json()["updated"] == 2
        lst = {t["id"]: t for t in client.get("/api/targets", headers=headers).json()}
        assert all(kol["id"] in {t["id"] for t in lst[i]["tags"]} for i in ids)

        # 批量移除
        r = client.post("/api/targets/batch-tags", headers=headers,
                        json={"target_ids": ids, "remove_tag_ids": [kol["id"]]})
        assert r.status_code == 200
        lst = {t["id"]: t for t in client.get("/api/targets", headers=headers).json()}
        assert all(kol["id"] not in {t["id"] for t in lst[i]["tags"]} for i in ids)

        # 空添加/移除 → 400
        r = client.post("/api/targets/batch-tags", headers=headers, json={"target_ids": ids})
        assert r.status_code == 400

        # ── 改名 / 换色 / target_count
        r = client.put(f"/api/tags/{kol['id']}", headers=headers, json={"name": "重点KOL", "color": "#F59E0B"})
        assert r.status_code == 200
        tags = {t["id"]: t for t in client.get("/api/tags", headers=headers).json()}
        assert tags[kol["id"]]["name"] == "重点KOL"
        assert tags[preset["id"]]["target_count"] == 1  # 只有账号甲还挂着预设

        # ── 删除标签：级联解除账号关联
        r = client.delete(f"/api/tags/{preset['id']}", headers=headers)
        assert r.status_code == 200 and r.json()["removed_links"] == 1
        lst = {t["id"]: t for t in client.get("/api/targets", headers=headers).json()}
        assert lst[ids[0]]["tags"] == []

        # ── 删除账号：关联一并清理（无孤儿 target_tags）
        r = client.delete(f"/api/targets/{ids[0]}", headers=headers)
        assert r.status_code == 204
        import sqlite3
        con = sqlite3.connect("data/intel_monitor.db")
        orphans = con.execute(
            "SELECT COUNT(*) FROM target_tags WHERE target_id NOT IN (SELECT id FROM targets)"
        ).fetchone()[0]
        con.close()
        assert orphans == 0
    finally:
        _cleanup(uname)
