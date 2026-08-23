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
set "TARGET_COUNT="
set /p "TARGET_COUNT=How many saved images per class? [96]: "
if not defined TARGET_COUNT set "TARGET_COUNT=96"
echo Selected target: %TARGET_COUNT% images per class.
echo The burst limit is computed to guarantee at least eight independent bursts
echo per class (normally 12 frames each). Use at least two capture sessions.
echo IMPORTANT: verify the whole gesture is clear in the MODEL INPUT preview.
echo.
"%TRAINING_PY%" scripts\01_capture.py --target-per-class "%TARGET_COUNT%" %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERROR] Capture ended with code %RESULT%.
pause
exit /b %RESULT%
