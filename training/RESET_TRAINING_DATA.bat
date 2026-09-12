@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo RESET - Delete all Rock/Paper/Scissors learning data
echo ================================================================
echo.
echo This removes captured RAW/PNG data, prepared splits, trained and
echo quantized models, STEdgeAI output, reports, and pipeline state.
echo.
echo It preserves scripts, configuration, the Python environment, and the
echo model currently embedded in the firmware so the board can still be
echo used to capture the replacement dataset.
echo.
echo Close Capture, VIEW_LIVE, the dataset review window, and any Explorer
echo window opened inside training. Dropbox locks are retried automatically.
echo.
echo WARNING: The local deletion is not undone by this script.
set /p RESET_CONFIRM=Type DELETE to continue: 
if not "%RESET_CONFIRM%"=="DELETE" (
    echo Reset cancelled. Nothing was changed.
    pause
    exit /b 1
)

call "%~dp0_env.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

"%TRAINING_PY%" "%~dp0scripts\reset_training_data.py" --confirm DELETE
set RESET_RC=%ERRORLEVEL%
if not "%RESET_RC%"=="0" echo Reset failed with exit code %RESET_RC%.
pause
exit /b %RESET_RC%
