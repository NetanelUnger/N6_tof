@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo N6 dual COM capture: ST-LINK INNER + USB CDC CLI
echo ================================================================
echo Close Tera Term on both COM ports before starting capture.
echo Each run creates two separate logs under training\reports\dual_com.
echo Type help for commands; quit to stop. Ctrl+C also closes ports.
echo Examples: status, ble status, wifi scan, inner a, bleprobe 45
echo USB replies appear here; INNER logs go to file unless --live-inner is set.
echo.
"%TRAINING_PY%" scripts\dual_com_debug.py %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
