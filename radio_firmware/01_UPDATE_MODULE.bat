@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================================
echo ST67W61 BLE/Wi-Fi module firmware update
echo ================================================================
echo Programs the bundled signed mission-T01 NCP image and LittleFS.
echo The process temporarily replaces the STM32 FSBL and always attempts to
echo restore it, including after a QConn failure. Follow each jumper prompt.
echo Stage 11 later verifies the live SDK version and BLE advertisement.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\Update-ST67Module.ps1" %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
