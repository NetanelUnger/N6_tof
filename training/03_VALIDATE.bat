@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 03 - Validate the raw dataset
echo ================================================================
echo Checks every NPZ against metadata and SHA-256, requires 54x42 uint16,
echo verifies companion PNGs, measures invalid pixels, class balance and exact
echo duplicates. The machine-readable report is reports\dataset_validation.json.
echo No source image is modified or deleted.
echo.
"%TRAINING_PY%" scripts\03_validate_dataset.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

