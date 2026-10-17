@echo off
REM Run again with input from nul: Ctrl+C then ends the launcher without cmd's
REM "Terminate batch job (Y/N)?" (the prompt reads nul and stops). The pauses below
REM read the console itself (<con).
if not "%~1"=="--launched" (
  call <nul "%~f0" --launched %*
  goto :eof
)
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
echo  This PC only. Stop or restart it from the editor's Settings,
echo  or Ctrl+C here.
echo ==========================================================
echo.

REM the browser opens on the first start only, not after a Restart
set "SM_OPEN=--auto-launch"
:run
"%SM%" serve --port %SM_PORT% %SM_OPEN%
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
