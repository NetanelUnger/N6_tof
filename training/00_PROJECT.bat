@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
"%TRAINING_PY%" scripts\00_project.py %*
set "RESULT=%ERRORLEVEL%"
if "%N6_NON_INTERACTIVE%"=="1" exit /b %RESULT%
if not "%RESULT%"=="0" pause
exit /b %RESULT%
