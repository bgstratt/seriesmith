@echo off
REM seriesmith - the editor on this PC only (http://127.0.0.1:8190)
REM run_seriesmith_ext.bat opens it to other devices on your network.

set "SM_PORT=8190"
set "SM=%~dp0.venv\Scripts\seriesmith.exe"
if not exist "%SM%" set "SM=seriesmith"

echo.
echo ==========================================================
echo  seriesmith is starting on port %SM_PORT%
echo.
echo   On this PC:   http://127.0.0.1:%SM_PORT%
echo.
echo  This PC only. Ctrl+C stops it.
echo ==========================================================
echo.

"%SM%" serve --port %SM_PORT%

echo.
echo If seriesmith didn't start: is the repo's .venv set up (INSTALL.md), or is
echo something else already on port %SM_PORT%?
pause
