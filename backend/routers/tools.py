# intel-monitor/backend/routers/tools.py
import shutil
import asyncio
import json as json_mod
import logging
import os
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
            daemon_running = r.status_code == 200
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
