@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
"%TRAINING_PY%" scripts\platform_check.py %*
set "RESULT=%ERRORLEVEL%"
if not "%N6_NON_INTERACTIVE%"=="1" pause
exit /b %RESULT%
