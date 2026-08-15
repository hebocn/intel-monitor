# intel-monitor/backend/tests/test_sync.py
"""「同步」功能测试：weibo 解析器 + POST /api/schedule/sync 接口（mock OpenCLI 拉取）。"""
import json
import time

from fastapi.testclient import TestClient
import main

from crawlers.opencli_crawler import _parse_weibo_posts


WEIBO_SAMPLE = [
    {
        "rank": 1, "id": "5112345678901234", "mblogid": "M1234AbC",
        "author": "测试博主", "uid": "1234567890",
        "text": "这是一条测试微博的正文内容。",
        "time": "Wed Jul 15 18:57:47 +0800 2026",
        "reposts": 3, "comments": 5, "likes": 12,
        "pic_count": 0, "url": "https://weibo.com/1234567890/M1234AbC",
    },
    {
        "rank": 2, "id": "5112345678901235", "mblogid": "M1234AbD",
        "author": "测试博主", "uid": "1234567890",
        "text": "第二条微博内容，带话题 #测试#。",
        "time": "Tue Jul 14 09:00:00 +0800 2026",
        "reposts": 0, "comments": 1, "likes": 7,
        "pic_count": 1, "url": "https://weibo.com/1234567890/M1234AbD",
    },
]


def test_parse_weibo_posts():
    posts = _parse_weibo_posts(WEIBO_SAMPLE)
    assert len(posts) == 2
    p = posts[0]
    assert p.content == "这是一条测试微博的正文内容。"
    assert p.likes == 12 and p.comments_count == 5 and p.shares == 3
    assert p.url == "https://weibo.com/1234567890/M1234AbC"
    assert p.author_name == "测试博主"
    assert p.published_at is not None  # 时间解析成功


def _cleanup(client, username):
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("DELETE FROM monitor_results WHERE target_id NOT IN (SELECT id FROM targets) AND target_id NOT IN (SELECT id FROM website_targets)")
    con.execute("DELETE FROM targets WHERE user_id NOT IN (SELECT id FROM users WHERE username != ?)", (username,))
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()


def test_sync_endpoint_success(monkeypatch):
    import routers.schedule as sched
    from crawlers.base import CrawlResult, PostData

    client = TestClient(main.app)
    uname = f"sync_test_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post("/api/targets", headers=headers, json={
        "platform": "weibo", "account_name": "测试博主",
        "account_url": "https://weibo.com/u/1234567890",
    })
    assert r.status_code == 201, r.text
    target_id = r.json()["id"]

    try:
        # mock 拉取：直接返回解析后的 posts
        async def _fake_crawl(platform, account_name, account_url, limit=10):
            assert platform == "weibo" and limit == 30
            return CrawlResult(
                success=True,
                posts=[PostData(url=p["url"], content=p["text"], title=p["text"][:40],
                                likes=p["likes"], comments_count=p["comments"],
                                shares=p["reposts"], author_name=p["author"])
                       for p in WEIBO_SAMPLE],
            )

        monkeypatch.setattr(sched, "crawl_with_opencli", _fake_crawl)
        monkeypatch.setattr(sched, "_check_opencli", lambda: True)

        r = client.post(f"/api/schedule/sync/{target_id}", headers=headers,
                        params={"limit": 30})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "success"
        assert body["posts_count"] == 2
        result_id = body["result_id"]

        # 详情接口能取到 raw_content
        rd = client.get(f"/api/results/{result_id}", headers=headers)
        assert rd.status_code == 200, rd.text
        posts = json.loads(rd.json()["raw_content"])
        assert posts[0]["content"] == "这是一条测试微博的正文内容。"
        assert rd.json().get("summary") in (None, "")
    finally:
        _cleanup(client, uname)


def test_sync_endpoint_unsupported_platform(monkeypatch):
    client = TestClient(main.app)
    uname = f"sync_bad_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.post("/api/targets", headers=headers, json={
        "platform": "youtube", "account_name": "某频道",
        "account_url": "https://youtube.com/@channel",
    })
    target_id = r.json()["id"]
    try:
        r = client.post(f"/api/schedule/sync/{target_id}", headers=headers, params={"limit": 10})
        assert r.status_code == 400, r.text
        assert "暂不支持" in r.json()["detail"]
    finally:
        _cleanup(client, uname)
