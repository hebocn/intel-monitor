@echo off
echo ============================
echo   情报监控平台 - 启动
echo ============================
echo.

:: Start backend
echo [1/2] Starting backend server at http://localhost:8000...
cd /d "%~dp0backend"
start "intel-monitor-backend" /B python main.py
cd /d "%~dp0"

:: Wait a moment for backend to start
timeout /t 2 /nobreak >nul

:: Start frontend dev server (hot reload, proxy /api to :8000)
echo [2/2] Starting frontend dev server at http://localhost:3000...
cd /d "%~dp0frontend"
start "intel-monitor-frontend" /B npm run dev
cd /d "%~dp0"

echo.
echo ============================
echo   Backend:  http://localhost:8000
echo   前端页面:  http://localhost:3000
echo   API 文档:  http://localhost:8000/docs
echo ============================
echo.
echo 修改前端代码后浏览器自动热更新，无需手工构建。
echo 按任意键退出...
pause >nul
