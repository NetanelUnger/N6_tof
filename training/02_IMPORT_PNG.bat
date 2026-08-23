@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 02 - Import an existing PNG dataset (optional)
echo ================================================================
echo Preferred layout: SOURCE\none, SOURCE\rock, SOURCE\paper,
echo SOURCE\scissors. Only 16-bit grayscale depth PNG preserves millimetres.
echo RGB preview images are rejected. 8-bit import requires --allow-8bit and
echo is marked approximate. SHA-256 makes reruns skip already imported files.
echo.
"%TRAINING_PY%" scripts\02_import_png.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

