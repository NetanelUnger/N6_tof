@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 08B - One-time Secure Neural-ART bootstrap through SWD
echo ================================================================
echo Neural-ART clocks, RIF permissions and SRAM3-6 access belong to Secure.
echo This builds/signs the complete chain, then programs ONLY FSBL + Secure.
echo Existing application slots and A/B metadata are preserved. Run this once
echo per board (or after changing Secure). BOOTCHAIN confirmation is required.
echo Use --build-only to verify artifacts without touching hardware.
echo.
"%TRAINING_PY%" scripts\08_bootstrap_secure.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
