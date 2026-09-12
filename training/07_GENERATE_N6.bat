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
rem This BAT is the interactive entry point. If the generated Neural-ART
rem artifacts are already current, Python asks whether to regenerate them.
rem Direct script/orchestrator calls remain non-interactive.
"%TRAINING_PY%" scripts\07_generate_n6.py --ask-force %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
