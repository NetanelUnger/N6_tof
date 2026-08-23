@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================================
echo Stage 00 - Build an isolated Python 3.11 environment
echo ================================================================
echo This creates training\.venv and installs pinned capture, image,
echo validation and TensorFlow packages. Existing dataset/model files stay.
echo The first installation can take several minutes and needs Internet.
echo.
where py >nul 2>nul || (echo [ERROR] Python launcher "py" was not found.& exit /b 1)
py -3.11 -c "import sys; print(sys.version)" || (
  echo [ERROR] Python 3.11 is required. Install the 64-bit CPython 3.11 runtime.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv...
  py -3.11 -m venv .venv || exit /b 1
) else (
  echo Reusing existing .venv; pip will install only missing/different packages.
)
".venv\Scripts\python.exe" -m pip install --upgrade pip wheel || exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1
".venv\Scripts\python.exe" scripts\00_setup.py || exit /b 1
".venv\Scripts\python.exe" scripts\self_test.py || exit /b 1
echo.
echo Setup complete. Next: 01_CAPTURE.bat
pause
