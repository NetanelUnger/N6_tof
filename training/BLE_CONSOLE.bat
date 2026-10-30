@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
"%TRAINING_PY%" scripts\ble_console.py %*
set "RESULT=%ERRORLEVEL%"
if "%~1"=="" if not "%RESULT%"=="0" pause
exit /b %RESULT%
