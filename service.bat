@echo off
chcp 65001 >nul
REM ============================================================
REM Fitness Nutrition Agent - one-click start / stop menu
REM   1 start   MCP 8010/8011, embed 8001, API 8000, UI 8501
REM   2 stop    kill the above via PID files / listening ports
REM   3 restart stop then start
REM   4 status  show what is running
REM Non-interactive: service.bat start|stop|restart|status
REM Keep REM and ECHO ASCII-simple: no carets/parens in echo.
REM ============================================================

cd /d "%~dp0"
set NO_PROXY=localhost,127.0.0.1
set no_proxy=localhost,127.0.0.1

if /i "%~1"=="start"   goto do_start
if /i "%~1"=="stop"    goto do_stop
if /i "%~1"=="restart" goto do_restart
if /i "%~1"=="status"  goto do_status
if not "%~1"=="" goto bad_arg

:menu
cls
echo ============================================================
echo            健身营养 Agent  -  一键启停
echo ============================================================
echo.
echo    [1] 启动全部服务
echo    [2] 停止全部服务
echo    [3] 重启
echo    [4] 查看运行状态
echo    [0] 退出
echo.
set /p choice=请输入选项后回车:
if "%choice%"=="1" goto do_start
if "%choice%"=="2" goto do_stop
if "%choice%"=="3" goto do_restart
if "%choice%"=="4" goto do_status
if "%choice%"=="0" exit /b 0
goto menu

REM ------------------------------------------------------------
:do_start
where uv >nul 2>nul
if errorlevel 1 (
    echo [ERROR] uv not found. Install: https://docs.astral.sh/uv/
    goto after_cmd
)
echo [1/3] Sync deps...
call uv sync
if errorlevel 1 goto after_cmd
echo.
echo [2/3] Start MCP bridges 8010/8011 ...
call uv run python scripts/start_mcp_servers.py up
echo.
echo [3/3] Start embedding bypass 8001, 10-60s ...
call uv run python scripts/start_embedding_server.py up
echo.
echo Start FastAPI 8000 and Streamlit 8501 ...
call :start_windowed
echo.
echo ============================================================
echo   Streamlit : http://localhost:8501
echo   FastAPI   : http://localhost:8000/docs
echo ============================================================
goto after_cmd

REM start API/UI only when their port is free
:start_windowed
call :port_pid 8000 _p
if defined _p (echo [skip] 8000 already running) else (
    start "Fitness Agent - FastAPI" cmd /k "uv run uvicorn app.main:app --host 127.0.0.1 --port 8000"
)
set _p=
call :port_pid 8501 _p
if defined _p (echo [skip] 8501 already running) else (
    start "Fitness Agent - Streamlit" cmd /k "uv run streamlit run ui/app.py"
)
set _p=
exit /b 0

REM ------------------------------------------------------------
:do_stop
echo Stop MCP bridges ...
call uv run python scripts/start_mcp_servers.py down
echo Stop embedding bypass ...
call uv run python scripts/start_embedding_server.py down
echo Stop FastAPI 8000 and Streamlit 8501 ...
call :kill_port 8000
call :kill_port 8501
echo Done.
goto after_cmd

REM ------------------------------------------------------------
:do_restart
call :do_stop
echo.
call :do_start
exit /b 0

REM ------------------------------------------------------------
:do_status
echo === MCP bridges ===
call uv run python scripts/start_mcp_servers.py status
echo.
echo === Embedding bypass ===
call uv run python scripts/start_embedding_server.py status
echo.
echo === Listening ports ===
call :show_port 8000 FastAPI
call :show_port 8001 Embed
call :show_port 8010 MCP-exercise
call :show_port 8011 MCP-nutrition
call :show_port 8501 Streamlit
goto after_cmd

:bad_arg
echo Unknown command: %~1
echo Use: start ^| stop ^| restart ^| status
exit /b 1

:after_cmd
if "%~1"=="" pause
exit /b 0

REM ============================================================
REM Subroutines
REM port_pid port outvar : set outvar to listening PID
:port_pid
set %2=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr LISTENING ^| findstr /C:":%1 "') do set %2=%%a
exit /b 0

REM kill_port port : taskkill listening PID with tree
:kill_port
call :port_pid %1 _kp
if defined _kp (
    echo   port %1 - PID %_kp
    taskkill /F /T /PID %_kp >nul 2>nul
) else (
    echo   port %1 not running
)
set _kp=
exit /b 0

REM show_port port label
:show_port
call :port_pid %1 _sp
if defined _sp (echo   [UP  ] %2 port %1 PID %_sp) else (echo   [DOWN] %2 port %1)
set _sp=
exit /b 0
