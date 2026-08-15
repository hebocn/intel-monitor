# intel-monitor/backend/routers/tools.py
import shutil
import asyncio
import json as json_mod
import logging
import os
import subprocess

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tools", tags=["tools"])


class OpenCLIStatusResponse:
    installed: bool
    daemon_running: bool


@router.get("/opencli-status")
def opencli_status():
    """检查 OpenCLI 安装状态"""
    installed = shutil.which("opencli") is not None
    daemon_running = False

    if installed:
        try:
            import httpx
            r = httpx.get("http://localhost:19825/status", timeout=3)
            # OpenCLI daemon 对未认证 HTTP 请求返回 403（仅 CLI/扩展带认证），
            # 因此只要收到任何 HTTP 响应（含 4xx）即说明 daemon 在运行。
            daemon_running = True
        except Exception:
            pass

    return {
        "installed": installed,
        "daemon_running": daemon_running,
    }


@router.get("/test-autocli")
async def test_autocli():
    """Debug: test autocli from within uvicorn process."""
    autocli_path = shutil.which("autocli")
    result = {
        "autocli_path": autocli_path,
        "path_env": os.environ.get("PATH", "")[:500],
        "which_result": None,
        "subprocess_test": None,
        "async_subprocess_test": None,
    }

    # Test sync subprocess
    try:
        import subprocess
        proc = subprocess.run(
            ["autocli", "weibo", "hot", "--format", "json", "--limit", "2"],
            capture_output=True, timeout=30,
        )
        result["subprocess_test"] = {
            "returncode": proc.returncode,
            "stdout_len": len(proc.stdout),
            "stderr_len": len(proc.stderr),
            "stdout_preview": proc.stdout[:200].decode("utf-8", errors="replace"),
            "stderr_preview": proc.stderr[:200].decode("utf-8", errors="replace"),
        }
    except Exception as e:
        result["subprocess_test"] = {"error": f"{type(e).__name__}: {repr(e)}"}

    # Test async subprocess
    try:
        proc = await asyncio.create_subprocess_exec(
            "autocli", "weibo", "hot", "--format", "json", "--limit", "2",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        result["async_subprocess_test"] = {
            "returncode": proc.returncode,
            "stdout_len": len(stdout),
            "stderr_len": len(stderr),
            "stdout_preview": stdout[:200].decode("utf-8", errors="replace"),
            "stderr_preview": stderr[:200].decode("utf-8", errors="replace"),
        }
    except Exception as e:
        result["async_subprocess_test"] = {"error": f"{type(e).__name__}: {repr(e)}"}

    return result


@router.get("/cdp-status")
async def cdp_status():
    """Check CDP Proxy + Chrome connectivity for XHS and Telegram search."""
    result = {
        "cdp_proxy_running": False,
        "chrome_connected": False,
        "chrome_port": None,
        "message": "",
        "diagnosis": "",
        "steps": [],
    }

    # 1. Check CDP Proxy health
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:3456/health")
            if resp.status_code == 200:
                data = resp.json()
                result["cdp_proxy_running"] = True
                result["chrome_connected"] = data.get("connected", False) or False
                result["chrome_port"] = data.get("chromePort")
    except Exception:
        pass

    # 2. Status message with actionable steps
    if not result["cdp_proxy_running"]:
        result["diagnosis"] = "CDP Proxy 未运行"
        result["message"] = "浏览器驱动代理未启动，小红书/Telegram 搜索不可用。"
        result["steps"] = [
            "1. 确保 Chrome 已启动，在地址栏访问 chrome://inspect/#remote-debugging，勾选 Enable",
            "2. 关闭所有 Chrome 窗口后重新打开，确保启用远程调试端口",
            "3. 双击项目根目录的 start.bat 重新启动（会自动拉起 CDP Proxy）",
            "4. 或手动运行：cd .claude\\skills\\web-access\\scripts && node cdp-proxy.mjs",
        ]
    elif not result["chrome_connected"]:
        result["diagnosis"] = "Chrome 远程调试未开启"
        result["message"] = "CDP Proxy 已运行，但 Chrome 未开启远程调试端口，无法操控浏览器。"
        result["steps"] = [
            "1. 完全关闭 Chrome（确保任务管理器中没有 chrome.exe 残留进程）",
            "2. 重新打开 Chrome，在地址栏输入 chrome://inspect/#remote-debugging",
            "3. 勾选 'Enable remote debugging for this browser instance'（开启后无需保持该页面打开）",
            "4. 刷新本页面，再次点击检测按钮",
        ]
    else:
        result["message"] = "CDP 连接正常，小红书/Telegram 搜索可用。"

    return result


@router.post("/cdp-repair")
async def cdp_repair():
    """Attempt to repair CDP connectivity automatically.

    Step 1: Ensure CDP Proxy is running (launch if needed).
    Step 2: Try to launch Chrome with remote debugging if none detected.
    Returns the result of each step so the frontend can show progress.
    """
    results = []
    chrome_port = None

    # ── Step 1: Ensure CDP Proxy is running ──────────────────────
    proxy_running = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get("http://localhost:3456/health")
            proxy_running = resp.status_code == 200
    except Exception:
        pass

    if not proxy_running:
        script = _find_cdp_proxy_script()
        if script and os.path.exists(script):
            try:
                subprocess.Popen(
                    ["node", script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # Wait up to 8 seconds for proxy to come online
                for _ in range(16):
                    await asyncio.sleep(0.5)
                    try:
                        async with httpx.AsyncClient(timeout=1) as c2:
                            r2 = await c2.get("http://localhost:3456/health")
                            if r2.status_code == 200:
                                proxy_running = True
                                break
                    except Exception:
                        continue
                if proxy_running:
                    results.append({"step": "启动 CDP Proxy", "ok": True})
                else:
                    results.append({"step": "启动 CDP Proxy", "ok": False, "detail": "启动超时，请检查 Node.js 是否安装"})
                    return {"success": False, "results": results, "message": "CDP Proxy 启动失败"}
            except FileNotFoundError:
                results.append({"step": "启动 CDP Proxy", "ok": False, "detail": "Node.js 未安装"})
                return {"success": False, "results": results, "message": "未找到 Node.js"}
            except Exception as e:
                results.append({"step": "启动 CDP Proxy", "ok": False, "detail": str(e)})
                return {"success": False, "results": results, "message": f"CDP Proxy 启动异常: {e}"}
        else:
            results.append({"step": "启动 CDP Proxy", "ok": False, "detail": "cdp-proxy.mjs 未找到"})
            return {"success": False, "results": results, "message": "cdp-proxy.mjs 文件缺失"}
    else:
        results.append({"step": "检查 CDP Proxy", "ok": True})

    # ── Step 2: Ensure Chrome is connected ───────────────────────
    chrome_connected = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:3456/health")
            if resp.status_code == 200:
                data = resp.json()
                chrome_connected = data.get("connected", False) or False
                chrome_port = data.get("chromePort")
    except Exception:
        pass

    if chrome_connected:
        results.append({"step": "连接 Chrome", "ok": True})
        return {"success": True, "results": results, "message": "CDP 已就绪，小红书/Telegram 搜索可用"}

    results.append({"step": "检测 Chrome 连接", "ok": False, "detail": "Chrome 未开启远程调试"})

    # ── Step 2b: Kill all Chrome, relaunch with --remote-debugging-port ──
    # Using the user's DEFAULT profile so XHS/Telegram login sessions persist.
    chrome_path = _find_chrome_exe()
    if not chrome_path:
        results.append({"step": "启动 Chrome 远程调试", "ok": False, "detail": "未找到 Chrome 安装路径"})
        return {
            "success": False, "results": results,
            "message": "未找到 Chrome，请手动安装后重试"
        }

    # Kill existing Chrome processes
    _kill_all_chrome()
    await asyncio.sleep(2)

    # Relaunch with user's real profile (preserves XHS/Telegram login cookies)
    user_profile = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "Google", "Chrome", "User Data"
    )
    try:
        subprocess.Popen(
            [chrome_path, "--remote-debugging-port=9222", f"--user-data-dir={user_profile}", "--restore-last-session"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        results.append({"step": "启动 Chrome 远程调试", "ok": False, "detail": str(e)})
        return {
            "success": False, "results": results,
            "message": f"Chrome 启动失败: {e}"
        }

    # Wait for Chrome to bind and CDP Proxy to detect it
    for _ in range(20):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=1) as c3:
                r3 = await c3.get("http://localhost:3456/health")
                if r3.status_code == 200:
                    data3 = r3.json()
                    if data3.get("connected"):
                        results.append({"step": "重启 Chrome 远程调试", "ok": True, "detail": "已用主 profile 重启 Chrome，登录态完整保留"})
                        return {"success": True, "results": results, "message": "Chrome 已重启，CDP 就绪，登录态已保留"}
        except Exception:
            continue

    results.append({"step": "启动 Chrome 远程调试", "ok": False, "detail": "Chrome 已启动但 CDP Proxy 未检测到连接"})
    return {
        "success": False, "results": results,
        "message": "Chrome 已重启但 CDP 仍未连接，请刷新页面后重试"
    }


def _find_cdp_proxy_script() -> str | None:
    """Find cdp-proxy.mjs relative to the project root."""
    this_file = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(this_file))
    candidates = [
        os.path.join(project_root, ".claude", "skills", "web-access", "scripts", "cdp-proxy.mjs"),
        os.path.join(project_root, "..", ".claude", "skills", "web-access", "scripts", "cdp-proxy.mjs"),
    ]
    for fp in candidates:
        if os.path.exists(fp):
            return fp
    return None


def _find_chrome_exe() -> str | None:
    """Find Chrome executable on Windows."""
    import winreg
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        candidates.append(os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"))
    for p in candidates:
        if os.path.exists(p):
            return p
    # Try registry
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
            val, _ = winreg.QueryValueEx(key, "")
            if val and os.path.exists(val):
                return val
    except Exception:
        pass
    return None


def _kill_all_chrome():
    """Kill all chrome.exe processes on Windows."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"],
                       capture_output=True, timeout=15)
    except Exception:
        pass


@router.get("/proxy/image")
async def proxy_image(url: str = Query(...)):
    """Proxy image requests to bypass CDN hotlink protection (e.g. Weibo)."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Only http/https URLs allowed")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "Referer": "https://weibo.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Upstream returned {resp.status_code}")
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=content_type)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
