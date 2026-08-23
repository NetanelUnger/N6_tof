@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 05 - Train the float reference model
echo ================================================================
echo Trains a deliberately small Conv2D classifier on the computer CPU/GPU.
echo Every epoch writes rps_checkpoint.keras and training_progress.json.
echo If interrupted, rerunning resumes only when data/config hashes match.
echo The held-out test split is evaluated only after training.
echo.

rem Explicit arguments preserve a non-interactive path for automation and
rem advanced use, for example: 05_TRAIN.bat --force
if not "%~1"=="" goto RUN_WITH_ARGUMENTS

:MENU
echo Choose how Stage 05 should run:
echo.
echo   [1] AUTO / RESUME  ^(recommended^)
echo       Reuse a current completed model, resume a compatible checkpoint,
echo       or start at epoch 1 when the data/configuration changed.
echo.
echo   [2] FRESH TRAINING FROM EPOCH 1  ^(--force^)
echo       Ignore the old model/checkpoint and train new weights from scratch.
echo       Raw captures and prepared train/validation/test data are NOT deleted.
echo.
echo   [3] SHOW PIPELINE STATUS
echo       Read the saved stage state and then return to this menu.
echo.
echo   [Q] CANCEL
echo.
choice /C 123Q /N /M "Select 1, 2, 3, or Q: "
if errorlevel 4 exit /b 0
if errorlevel 3 goto SHOW_STATUS
if errorlevel 2 goto RUN_FRESH
if errorlevel 1 goto RUN_AUTO

:SHOW_STATUS
echo.
"%TRAINING_PY%" scripts\pipeline_status.py
echo.
goto MENU

:RUN_FRESH
echo.
echo [FRESH] Starting a new model at epoch 1. Dataset files are preserved.
"%TRAINING_PY%" scripts\05_train_model.py --force
goto FINISH

:RUN_AUTO
echo.
echo [AUTO] Reusing or resuming only artifacts compatible with current inputs.
"%TRAINING_PY%" scripts\05_train_model.py
goto FINISH

:RUN_WITH_ARGUMENTS
echo [NON-INTERACTIVE] Running Stage 05 with arguments: %*
"%TRAINING_PY%" scripts\05_train_model.py %*

:FINISH
set "RESULT=%ERRORLEVEL%"
if "%RESULT%"=="0" echo [DONE] Stage 05 completed successfully.
if not "%RESULT%"=="0" echo [FAILED] Stage 05 returned error code %RESULT%.
pause
exit /b %RESULT%
