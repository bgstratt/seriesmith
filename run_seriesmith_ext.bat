@echo off
REM Run again with input from nul: Ctrl+C then ends the launcher without cmd's
REM "Terminate batch job (Y/N)?" (the prompt reads nul and stops). The pauses below
REM read the console itself (<con).
if not "%~1"=="--launched" (
  call <nul "%~f0" --launched %*
  goto :eof
)
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

REM the browser opens on the first start only, not after a Restart
set "SM_OPEN=--auto-launch"
:run
"%SM%" serve --host 0.0.0.0 --port %SM_PORT% %SM_OPEN%
REM 3: the editor's Restart (or `seriesmith stop --restart`) - start it again
if errorlevel 3 if not errorlevel 4 (
  echo.
  echo  seriesmith is restarting...
  set "SM_OPEN="
  goto run
)
REM 0: stopped on purpose (the editor's Stop, `seriesmith stop`, Ctrl+C / Ctrl+Break)
if not errorlevel 1 (
  echo.
  echo  seriesmith stopped.
  timeout /t 3 <con >nul
  exit /b 0
)

echo.
echo If seriesmith didn't start: is the repo's .venv set up (INSTALL.md), or is
echo something else already on port %SM_PORT%?
pause <con
