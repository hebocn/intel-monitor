# -*- coding: utf-8 -*-
"""
X 登录辅助脚本 — 为 twitter 热门榜单抓取准备登录态。

用法:
    cd backend
    python scripts/login_x.py

在打开的浏览器中登录 X(账号密码/验证码),登录成功后直接关闭浏览器窗口,
登录态会自动保存到 backend/data/x_profile,之后热门话题模块即可抓取 twitter 榜单。
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    user_data_dir = Path(__file__).resolve().parents[1] / "data" / "x_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    print(f"登录态将保存到: {user_data_dir}")
    print("请在打开的浏览器中登录 X,登录成功后关闭浏览器窗口即可。")

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=str(user_data_dir),
        headless=False,
        args=["--no-sandbox"],
    )
    page = await context.new_page()
    await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
    print("浏览器已打开,请登录...")

    # 等待用户关闭浏览器窗口
    try:
        while len(context.pages) > 0:
            await asyncio.sleep(2)
    finally:
        try:
            await context.close()
        except Exception:
            pass
        await pw.stop()
    print("登录态已保存,现在可以抓取 twitter 热门榜单了。")


if __name__ == "__main__":
    asyncio.run(main())
