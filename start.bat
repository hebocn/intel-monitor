@echo off
chcp 65001 >nul
echo ============================
echo    Intel Monitor - Launch
echo ============================
echo.

:: ── 0. Ensure Chrome CDP is available ────────────────────────
echo [0/3] Checking Chrome remote debugging port...
set "CDP_PORT=9222"
set "CHROME_READY=0"

powershell -NoProfile -Command "$tcp=New-Object System.Net.Sockets.TcpClient; try{$tcp.Connect('127.0.0.1',9222);$tcp.Close();exit 0}catch{exit 1}" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   Chrome CDP port 9222 already available.
    set "CHROME_READY=1"
    goto :skip_chrome_launch
)

echo   Chrome CDP port not found, searching for Chrome...

set "CHROME_PATH="

:: Try registry first
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'^(Default^)'" 2^>nul`) do set "CHROME_PATH=%%i"

if not defined CHROME_PATH (
    for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "(Get-ItemProperty 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe' -ErrorAction SilentlyContinue).'^(Default^)'" 2^>nul`) do set "CHROME_PATH=%%i"
)

:: Fallback: common paths
if not defined CHROME_PATH (
    if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
)
if not defined CHROME_PATH (
    if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)
if not defined CHROME_PATH (
    if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

if defined CHROME_PATH (
    echo   Found: %CHROME_PATH%
    echo   Launching with --remote-debugging-port=9222...
    start "" "%CHROME_PATH%" --remote-debugging-port=9222
    timeout /t 4 /nobreak >nul
    set "CHROME_READY=1"
    echo   Chrome launched.
) else (
    echo   [WARN] Chrome not found. CDP proxy will start but cannot connect.
)

:skip_chrome_launch

:: ── 1. Start CDP Proxy ───────────────────────────────────────
echo [1/3] Starting CDP Proxy...
:: CDP Proxy uses browser-discovery to auto-detect Chrome with
:: the remote-debugging toggle enabled (chrome://inspect#remote-debugging).
:: No need to launch a separate Chrome -- the Proxy connects
:: to the user's existing Chrome instance with all login sessions intact.
if exist ".claude\skills\web-access\scripts\cdp-proxy.mjs" (
    pushd ".claude\skills\web-access\scripts"
    start "intel-monitor-cdp-proxy" /B node cdp-proxy.mjs
    popd
    echo   CDP Proxy launched on port 3456.
    echo   It will auto-discover Chrome via chrome://inspect#remote-debugging.
) else (
    echo   [WARN] cdp-proxy.mjs not found, skipping.
)

:: ── 2. Start backend ─────────────────────────────────────────
echo [2/3] Starting backend at http://localhost:8000...
if exist "backend\main.py" (
    cd /d "%~dp0backend"
    start "intel-monitor-backend" /B python main.py
    cd /d "%~dp0"
    timeout /t 3 /nobreak >nul
    echo   Backend launched.
) else (
    echo   [ERROR] backend\main.py not found.
)

:: ── 3. Start frontend ────────────────────────────────────────
echo [3/3] Starting frontend at http://localhost:3000...
if exist "frontend\package.json" (
    pushd "frontend"
    start "intel-monitor-frontend" /B npm run dev
    popd
    echo   Frontend launched.
) else (
    echo   [ERROR] frontend\package.json not found.
)

echo.
echo ============================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo   API docs: http://localhost:8000/docs
if "%CHROME_READY%"=="1" (
    echo   CDP Proxy: http://localhost:3456 ^(Chrome CDP: 9222^)
) else (
    echo   [WARN] No Chrome CDP -- XHS/Douyin search unavailable
)
echo ============================
echo.
echo Press any key to exit...
pause >nul
