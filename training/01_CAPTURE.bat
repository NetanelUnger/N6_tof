@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 01 - Guided continuous ToF capture
echo ================================================================
echo The program auto-detects CN8, disables the ANSI MAP stream and enables
echo DATASET STREAM ON. Every frame is CRC checked and frame IDs must progress.
echo SPACE starts/stops one burst. Move the hand/object in angle and depth.
echo Separate bursts are kept intact during train/validation/test splitting.
echo Exact uint16 millimetres are saved as NPZ plus 16-bit depth PNG; RGB PNG
echo is only a human preview. Closing the window safely stops the FW stream.
echo A session-specific capture.log records CRC, timeout and frame diagnostics.
echo Existing sessions are never erased. Resume one with:
echo   01_CAPTURE.bat --session SESSION_NAME
echo.

rem With no arguments, present a guided menu for new/resumed/custom capture.
rem Explicit arguments preserve the original advanced/non-interactive path.
if not "%~1"=="" goto RUN_WITH_ARGUMENTS
"%TRAINING_PY%" scripts\01_capture_menu.py
goto FINISH

:RUN_WITH_ARGUMENTS
echo [ARGUMENT MODE] Running capture with: %*
"%TRAINING_PY%" scripts\01_capture.py %*

:FINISH
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERROR] Capture ended with code %RESULT%.
pause
exit /b %RESULT%
