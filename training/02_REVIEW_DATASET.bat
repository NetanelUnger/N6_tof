@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 02 - Human review of captured dataset
echo ================================================================
echo Raw captures are never deleted or edited. Accept, Reject and Relabel are
echo stored in review\dataset_review.json and are applied by Capture, Validate,
echo Prepare and the HTML analysis. Suspicious frames are shown first, but the
echo model never rejects a frame automatically.
echo.
"%TRAINING_PY%" scripts\02_review_dataset.py %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" echo [ERROR] Dataset review ended with code %RESULT%.
pause
exit /b %RESULT%
