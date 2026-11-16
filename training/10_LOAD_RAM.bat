@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
echo ================================================================
echo Development lane - incremental build and complete NPU SRAM boot
echo ================================================================
echo Builds a guarded Non-Secure/model RAM candidate and loads it with the
echo checked DEV loader with an FSBL metadata-write guard.
echo First reset into DEV: BOOT0=1-2, BOOT1=2-3. Pass --board-serial.
echo Use --keep-network to retain saved Wi-Fi/Cloud intent; default: BLE only.
echo NCP settings are preserved. No reset is sent by this loader.
echo The original Debug artifacts and source build flags are restored.
echo An explicit --version affects only that RAM candidate; RESET loses it.
echo.
"%TRAINING_PY%" scripts\deploy_firmware.py --ram %*
set "RESULT=%ERRORLEVEL%"
if not "%N6_NON_INTERACTIVE%"=="1" pause
exit /b %RESULT%
