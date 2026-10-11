@echo off
REM seriesmith - the editor, reachable from other devices on your LAN
REM --host 0.0.0.0 listens on every network interface (as ComfyUI's --listen)
REM --port 8190 is the default; change it here if you want a different one

set "SM_PORT=8190"
set "SM=%~dp0.venv\Scripts\seriesmith.exe"
if not exist "%SM%" set "SM=seriesmith"

REM Find the LAN IP of the adapter that actually has a default gateway
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up'} | Select-Object -First 1 -ExpandProperty IPv4Address).IPAddress"`) do set "LANIP=%%a"

echo.
echo ==========================================================
echo  seriesmith is starting on port %SM_PORT%
echo.
echo   On this PC:        http://127.0.0.1:%SM_PORT%
if defined LANIP echo   Laptop / phone:    http://%LANIP%:%SM_PORT%
echo.
echo  Both devices must be on the same network/Wi-Fi.
echo  There is NO password on this - anyone on the network can
echo  open your project folders, import files from this PC, see
echo  the API key in Settings and queue paid runs. Home Wi-Fi
echo  you trust only; never port-forward it.
echo ==========================================================
echo.

"%SM%" serve --host 0.0.0.0 --port %SM_PORT%

echo.
echo If seriesmith didn't start: is the repo's .venv set up (INSTALL.md), or is
echo something else already on port %SM_PORT%?
pause
