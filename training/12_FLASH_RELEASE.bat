@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
echo ================================================================
echo Stage 12 - signed update package / existing installation workflow
echo ================================================================
echo --package-only --version N requires the exact Stage10/11 RAM candidate.
echo It signs the tested code and weights without rebuilding or modifying HW.
echo Its version must already be current+1 inside the accepted RAM candidate.
echo Persistent installation remains a separate existing confirmed operation.
echo.
"%TRAINING_PY%" scripts\deploy_firmware.py --flash %*
set "RESULT=%ERRORLEVEL%"
if not "%N6_NON_INTERACTIVE%"=="1" pause
exit /b %RESULT%
