@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
echo ================================================================
echo Development lane - incremental build and complete NPU SRAM boot
echo ================================================================
echo Builds a guarded Non-Secure/model RAM candidate and loads it with the
echo existing Secure DEV boot lane. NCP settings are preserved read-only.
echo The original Debug artifacts and source build flags are restored.
echo An explicit --version affects only that RAM candidate; RESET loses it.
echo.
"%TRAINING_PY%" scripts\deploy_firmware.py --ram %*
set "RESULT=%ERRORLEVEL%"
if not "%N6_NON_INTERACTIVE%"=="1" pause
exit /b %RESULT%
