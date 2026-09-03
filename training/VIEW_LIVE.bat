@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo N6 live viewer - complete atomic N6DF v3 frames
echo ================================================================
echo This viewer receives full-rate raw and exact NPU images. It swaps the
echo screen only after dimensions, frame ID, payload lengths and CRCs pass.
echo Tera Term must be closed because only one program can own CN8.
echo With no arguments, the next screen lists every COM port and marks CN8.
echo To bypass the menu: VIEW_LIVE.bat --port COM8
echo.
"%TRAINING_PY%" scripts\live_view.py %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
