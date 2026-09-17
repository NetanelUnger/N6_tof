@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Checking the bundled ST67W61 update package...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Test-ST67Package.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
