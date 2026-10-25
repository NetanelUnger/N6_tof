@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Checking the bundled ST67W61 update package...
echo Verified text line-ending differences are repaired automatically.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Test-ST67Package.ps1"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
