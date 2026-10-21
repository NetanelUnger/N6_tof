@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat %* || exit /b
echo ================================================================
echo Stage 01 - Guided continuous ToF capture
echo ================================================================
echo Select USB, BLE or Cloud in the capture window. The source verifies the
echo device before streaming. Original records are integrity checked before save.
echo SPACE starts/stops one burst. Move the hand/object in angle and depth.
echo Separate bursts are kept intact during train/validation/test splitting.
echo Exact uint16 millimetres are saved as NPZ plus 16-bit depth PNG; RGB PNG
echo is only a human preview. Closing the window safely stops the FW stream.
echo A session-specific capture.log records CRC, timeout and frame diagnostics.
echo Existing sessions are never erased. Resume one with:
echo   01_CAPTURE.bat --session SESSION_NAME
echo.

"%TRAINING_PY%" scripts\01_capture.py %*

:FINISH
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERROR] Capture ended with code %RESULT%.
if not "%N6_NON_INTERACTIVE%"=="1" pause
exit /b %RESULT%
