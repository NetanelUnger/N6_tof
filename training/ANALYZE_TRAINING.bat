@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b

echo ================================================================
echo N6 Training Analysis - interactive Hebrew HTML report
echo ================================================================
echo Reads the captured dataset, prepared splits, model reports and HIL.
echo It does NOT train, change raw data, replace a model, build firmware,
echo or access the board. It only creates a new report under reports\html.
echo.

"%TRAINING_PY%" scripts\analyze_training.py --open %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" (
  echo.
  echo [FAILED] Analysis returned error code %RESULT%.
  pause
)
exit /b %RESULT%
