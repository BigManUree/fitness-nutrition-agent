@echo off
REM Launch Cloudflare Quick Tunnel (keep this window open).
REM --protocol http2: force TCP; UDP/QUIC drops behind Clash.
REM --edge-ip-version 4: IPv4 only to avoid broken IPv6 reconnects.
title Cloudflare Quick Tunnel
cd /d "%~dp0\.."

echo Starting tunnel, please keep this window open...
echo.
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8501 --no-autoupdate --protocol http2 --edge-ip-version 4

echo.
echo === Tunnel stopped. If an error is shown above, screenshot it. ===
pause
