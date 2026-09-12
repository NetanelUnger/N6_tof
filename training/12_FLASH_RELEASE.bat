@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 12 - signed incremental build and CN8 XMODEM flash update
echo ================================================================
echo This is persistent and increments the tracked firmware version by exactly
echo one. It signs Non-Secure, creates .n6fw, sends it through USB CDC/XMODEM,
echo resets and verifies the version after the trial confirmation window.
echo It asks for the word FLASH before modifying the board.
echo The embedded weights travel inside the same signed A/B application image.
echo This gate requires Stage 09 Secure bootstrap and a passing Stage 11 HIL for
echo the exact current model. Add --package-only to build without touching HW.
echo After a RAM HIL, return BOOT0 and BOOT1 to 1-2 WITHOUT pressing RESET;
echo keep the validated RAM image running so XMODEM can install and then reset.
echo.
"%TRAINING_PY%" scripts\deploy_firmware.py --flash %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
