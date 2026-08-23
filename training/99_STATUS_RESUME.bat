@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Pipeline status / resume assistant
echo ================================================================
echo Reads only metadata, state manifests and model artifacts. Nothing changes.
echo Resume by running the first incomplete numbered BAT; existing compatible
echo outputs are reused and raw captures are always appended, never erased.
echo.
"%TRAINING_PY%" scripts\pipeline_status.py
pause

