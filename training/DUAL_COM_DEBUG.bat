@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
echo ================================================================
echo N6 dual COM capture: ST-LINK INNER + USB CDC CLI
echo ================================================================
echo Close Tera Term on both COM ports before starting capture.
echo Each run creates two separate logs under training\reports\dual_com.
echo ESC switches interactive SEND and LIVE DISPLAY between USB CDC and UART.
echo USB: type CLI and Enter. UART: press one-key commands without Enter.
echo Press ESC again to switch back. Both COM ports continue logging.
echo Type help for commands; quit to stop. Ctrl+C also closes ports.
echo Examples: status, ble status, wifi scan, inner a, bleprobe 45
echo Default live view is USB. --live-inner shows both until the first ESC.
echo.
"%TRAINING_PY%" scripts\dual_com_debug.py %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
