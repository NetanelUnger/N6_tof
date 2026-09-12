@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call _env.bat || exit /b
echo ================================================================
echo Stage 06 - Full-integer TFLite quantization
echo ================================================================
echo Uses real training samples as the representative dataset, requires a
echo genuine uint8 scale=1 input with no CAST and an int8 output, then runs the
echo complete test set through the
echo TFLite interpreter. models\model_contract.json freezes tensor shapes,
echo scales, zero points, class order and preprocessing for the firmware.
echo.
"%TRAINING_PY%" scripts\06_quantize_model.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
