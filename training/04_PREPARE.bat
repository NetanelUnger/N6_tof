@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 04 - Freeze preprocessing and create data splits
echo ================================================================
echo Converts millimetres to the documented 64x50x1 uint8 NPU input.
echo A complete SPACE burst stays in one split, preventing nearly identical
echo neighboring frames from appearing in both training and testing.
echo Input/config hashes make an unchanged rerun a fast no-op.
echo.
"%TRAINING_PY%" scripts\04_prepare_dataset.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%

