@echo off
chcp 65001 >nul
REM ============================================================
REM Fitness Nutrition Agent - one-click launcher (interactive)
REM Opens the PowerShell multi-round service manager menu.
REM Keep REM ASCII-only: cmd mis-parses CJK in comments.
REM ============================================================

cd /d "%~dp0"
set NO_PROXY=localhost,127.0.0.1
set no_proxy=localhost,127.0.0.1

where powershell >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PowerShell not found on this system.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage.ps1"
