@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 08 - Integrate Neural-ART code and weights into firmware
echo ================================================================
echo Installs the matching STAI/LL_ATON runtime and generated network sources.
echo The raw weight blob is embedded inside the signed Non-Secure image, then
echo copied to NPU SRAM6 at boot. Therefore the existing .n6fw v1 A/B update is
echo atomic: app code and its exact weights always install/rollback together.
echo.
"%TRAINING_PY%" scripts\08_integrate_model.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
