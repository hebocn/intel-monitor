# intel-monitor/backend/tests/test_manual_run_push.py
"""「立即执行」(POST /api/schedule/run) 后必须触发飞书推送。

模拟真实链路：注册用户 → 创建目标 → POST run → BackgroundTasks 执行
execute_monitor → 断言 push_monitor_result 被调用（社交账号 + 网站）。
"""
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import main

import services.monitor as monitor_mod

called: list[tuple] = []


async def _fake_push(target_type: str, target_id: int):
    called.append((target_type, target_id))


class FakePost:
    title = "测试标题"
    content = "测试内容"
    url = "https://example.com/post/1"
    likes = 10
    comments_count = 2
    images = []
    author_name = "测试作者"
    author_avatar = None
    published_at = None


def _cleanup(client: TestClient, username: str):
    import sqlite3
    con = sqlite3.connect("data/intel_monitor.db")
    con.execute("DELETE FROM monitor_results WHERE target_id NOT IN (SELECT id FROM targets) AND target_id NOT IN (SELECT id FROM website_targets)")
    con.execute("DELETE FROM targets WHERE user_id NOT IN (SELECT id FROM users WHERE username != ?)", (username,))
    con.execute("DELETE FROM website_targets WHERE user_id NOT IN (SELECT id FROM users WHERE username != ?)", (username,))
    con.execute("DELETE FROM users WHERE username=?", (username,))
    con.commit()
    con.close()


def test_manual_run_social_pushes_feishu(monkeypatch):
    client = TestClient(main.app)
    uname = f"push_social_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # 创建社交目标
    r = client.post("/api/targets", headers=headers, json={
        "platform": "weibo", "account_name": "测试号", "account_url": "https://weibo.com/u/123",
    })
    assert r.status_code == 201, r.text
    target_id = r.json()["id"]

    try:
        # stub 爬虫与摘要，monkeypatch 推送记录
        called.clear()
        monkeypatch.setattr(monitor_mod, "push_monitor_result", _fake_push)

        async def _fake_crawl(platform, account_name, account_url, post_limit=10, post_time_range_days=0):
            return SimpleNamespace(success=True, posts=[FakePost()], error_message=None), "test", []

        monkeypatch.setattr(monitor_mod, "crawl_with_fallback", _fake_crawl)

        async def _fake_summarize(platform, account_name, posts):
            return "测试摘要内容"

        monkeypatch.setattr(monitor_mod.summarizer, "summarize_posts", _fake_summarize)

        # 立即执行
        r = client.post(f"/api/schedule/run/{target_id}", headers=headers,
                        params={"target_type": "social_media"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending"

        # BackgroundTasks 在 TestClient 响应后已同步执行
        assert ("social_media", target_id) in called, f"未推送: {called}"
    finally:
        _cleanup(client, uname)


def test_manual_run_website_pushes_feishu(monkeypatch):
    client = TestClient(main.app)
    uname = f"push_site_{int(time.time())}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "testpass123"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post("/api/websites", headers=headers, json={
        "name": "测试网站", "url": "https://example.com",
    })
    assert r.status_code == 201, r.text
    site_id = r.json()["id"]

    try:
        called.clear()
        monkeypatch.setattr(monitor_mod, "push_monitor_result", _fake_push)

        async def _fake_crawl_in_thread(fn, *a, **kw):
            return SimpleNamespace(success=True, posts=[SimpleNamespace(content="网站内容")])

        monkeypatch.setattr(monitor_mod, "_run_crawler_in_thread", _fake_crawl_in_thread)

        async def _fake_summarize_website(name, content):
            return "网站摘要内容"

        monkeypatch.setattr(monitor_mod.summarizer, "summarize_website", _fake_summarize_website)

        r = client.post(f"/api/schedule/run/{site_id}", headers=headers,
                        params={"target_type": "website"})
        assert r.status_code == 200, r.text

        assert ("website", site_id) in called, f"未推送: {called}"
    finally:
        _cleanup(client, uname)
