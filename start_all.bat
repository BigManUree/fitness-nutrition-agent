@echo off
chcp 65001 >nul
REM ============================================================
REM Fitness Nutrition Agent - one-click startup
REM   1. MCP bridges  (8010 exerciseapi / 8011 nutrition-mcp)
REM   2. Embedding    (8001, optional - failure does not block)
REM   3. FastAPI      (8000)
REM   4. Streamlit    (8501)
REM Already-running services are auto-skipped; safe to re-run.
REM NOTE: keep REM lines ASCII-only - cmd mis-parses CJK bytes
REM in comments when switching console codepage.
REM ============================================================

cd /d "%~dp0"

REM Bypass system proxies (e.g. Clash) for localhost probes
set NO_PROXY=localhost,127.0.0.1
set no_proxy=localhost,127.0.0.1

where uv >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 uv，请先安装：https://docs.astral.sh/uv/
    pause
    exit /b 1
)

echo [1/4] 检查依赖（首次运行需要一点时间）...
call uv sync
if errorlevel 1 goto :fail

echo.
echo [2/4] 启动 MCP 数据桥接（8010 / 8011）...
call uv run python scripts/start_mcp_servers.py up
if errorlevel 1 (
    echo [警告] MCP 桥接启动异常，计划生成可能失败。
)

echo.
echo [3/4] 启动嵌入服务（8001，约需 10-60 秒加载模型）...
call uv run python scripts/start_embedding_server.py up
if errorlevel 1 (
    echo [提示] 嵌入服务未启动，不影响计划生成，仅画像语义检索不可用。
)

echo.
echo [4/4] 启动 FastAPI（8000）与 Streamlit（8501）...
start "Fitness Agent - FastAPI" cmd /k "uv run uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Fitness Agent - Streamlit" cmd /k "uv run streamlit run ui/app.py"

echo.
echo ============================================================
echo  全部启动指令已发出，等待数秒让服务就绪：
echo    Streamlit 界面 : http://localhost:8501
echo    FastAPI 文档   : http://localhost:8000/docs
echo    FastAPI 健康检查: http://localhost:8000/health
echo.
echo  关闭服务：直接关掉弹出的两个窗口，并执行
echo    uv run python scripts/start_mcp_servers.py down
echo    uv run python scripts/start_embedding_server.py down
echo ============================================================
echo.
echo 本窗口 10 秒后自动关闭...
REM ping instead of timeout: GNU coreutils timeout in PATH shadows it
ping -n 11 127.0.0.1 >nul
exit /b 0

:fail
echo [错误] 启动失败，请根据上方提示排查。
pause
exit /b 1
