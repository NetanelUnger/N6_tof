@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 07 - Compile TFLite for STM32N6 Neural-ART
echo ================================================================
echo Requires ST's STEdgeAI Core CLI. Set STEDGEAI_PATH to stedgeai.exe or its
echo directory. C:\ST\STEdgeAI versioned installs are detected automatically.
echo The script invokes --target stm32n6 --st-neural-art and rejects
echo output that does not contain Neural-ART/LL_ATON code or weight blobs.
echo It never silently falls back to Cortex-M55 inference.
echo.
"%TRAINING_PY%" scripts\07_generate_n6.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
