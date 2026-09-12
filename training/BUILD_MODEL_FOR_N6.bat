@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Resumable model build: validate - prepare - train - quantize - Neural-ART
echo ================================================================
echo Each stage fingerprints its inputs. Unchanged prepared artifacts are reused,
echo and interrupted training resumes from its compatible epoch checkpoint.
echo This orchestrator stops immediately on a real error or missing ST tool.
echo.
for %%S in (03_validate_dataset.py 04_prepare_dataset.py 05_train_model.py 06_quantize_model.py 07_generate_n6.py) do (
  echo.
  echo -------- Running %%S --------
  "%TRAINING_PY%" "scripts\%%S"
  if errorlevel 1 (
    echo [STOP] %%S did not complete. Fix the reported prerequisite and rerun this BAT.
    pause
    exit /b 1
  )
)
echo.
echo Model generation finished. Installing the atomic firmware integration...
"%TRAINING_PY%" scripts\08_integrate_model.py
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" echo [DONE] Model code and weights are one signed A/B firmware unit.
pause
exit /b %RESULT%
