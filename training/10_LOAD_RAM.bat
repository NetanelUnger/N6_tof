@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Development lane - incremental build and complete NPU SRAM boot
echo ================================================================
echo Builds Secure and Non-Secure incrementally, then loads the local Secure
echo image into SRAM1 and Non-Secure/model into SRAM2 via the DEV-boot FSBL.
echo No signing, no flash write, no firmware-version increment. RESET loses it.
echo Use this after FW/data-stream changes for the fastest feedback loop.
echo.
"%TRAINING_PY%" scripts\10_build_upload.py --ram %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
