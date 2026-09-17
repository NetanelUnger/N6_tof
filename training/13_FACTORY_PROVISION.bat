@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0\.."
echo ================================================================
echo Factory-new external Flash provisioning
echo ================================================================
echo DESTRUCTIVE: erases the complete external NOR, including both A/B slots
echo and boot metadata. It then rebuilds, signs, programs, verifies, and boots
echo FSBL + Secure + application slot A as if the board were new.
echo.
echo Required before erase: BOOT0=1-2, BOOT1=2-3, ST-LINK connected, RESET.
echo Required after write:  BOOT0=1-2, BOOT1=1-2, CN8 connected, RESET.
echo Pass -BuildOnly to build and verify artifacts without erasing hardware.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Tools\Factory-Provision.ps1" %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
