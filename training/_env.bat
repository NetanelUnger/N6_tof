@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "TRAINING_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%TRAINING_PY%" (
  echo.
  echo [ERROR] The isolated Python environment does not exist.
  echo Run 00_SETUP.bat once, then repeat this stage.
  exit /b 2
)
"%TRAINING_PY%" -c "import sys; assert sys.version_info[:2] == (3,11), sys.version"
if errorlevel 1 exit /b 3
endlocal & set "TRAINING_PY=%TRAINING_PY%"
exit /b 0

